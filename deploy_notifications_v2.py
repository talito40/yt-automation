"""
deploy_notifications_v2.py

Two fixes:
1. main.py  — send immediate Telegram on each upload (main + each Short separately)
2. monitor.py — per-video view tracking (regular + Shorts tracked individually)
"""

import paramiko, py_compile, tempfile, os, sys

HOST, USER, PASSWD = "165.22.33.167", "root", "LukaKi2001q"
REMOTE = "/opt/yt-automation"

# ── 1. main.py — immediate per-upload notifications ───────────────────────────
MAIN_PY = '''\
"""
main.py -- YouTube Automation  |  Daily pipeline orchestrator
"""

import argparse
import json
import os
import sys
import traceback
import requests
from datetime import date, datetime

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--channel", type=int, default=1)
_pre_args, _ = _pre.parse_known_args()
os.environ["CHANNEL"] = str(_pre_args.channel)

import content_generator
import video_generator
import youtube_uploader
import thumb_generator
import avatar_generator
import video_stitcher
import config

USED_TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE         = f"pipeline_ch{config.CHANNEL}.log"


def _log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\\n")


def _load_used_topics():
    if os.path.exists(USED_TOPICS_FILE):
        with open(USED_TOPICS_FILE) as f:
            return json.load(f)
    return []


def _save_used_topic(topic):
    topics = _load_used_topics()
    topics.append(topic)
    with open(USED_TOPICS_FILE, "w") as f:
        json.dump(topics, f, indent=2)


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _notify(msg):
    """Send a Telegram message immediately."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def _upload_short(service, video_package, main_url, angle, suffix):
    today      = date.today().isoformat()
    short_path = f"short_{today}_{suffix}.mp4"
    try:
        shorts_pkg = content_generator.generate_shorts_script(video_package, angle=angle)
        shorts_pkg["description"] = shorts_pkg.get("description", "").replace("[MAIN_VIDEO_URL]", main_url)
        video_generator.generate_shorts_video(
            title=shorts_pkg["title"],
            script=shorts_pkg["script"],
            scenes=shorts_pkg.get("scenes"),
            output_path=short_path,
        )
        short_url, short_id = youtube_uploader.upload_short(
            video_path=short_path,
            title=shorts_pkg["title"],
            description=shorts_pkg.get("description", ""),
            tags=shorts_pkg.get("tags", []),
            service=service,
        )
        return short_url, shorts_pkg["title"]
    except Exception as exc:
        _log(f"  Short ({angle}) failed (non-fatal): {exc}")
        return None, None
    finally:
        _cleanup(short_path)


def run_pipeline():
    today      = date.today().isoformat()
    raw_path   = f"video_raw_{today}.mp4"
    video_path = f"video_{today}.mp4"
    intro_path = f"intro_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"

    try:
        # 1 -- SEO topic research
        _log("Step 1/6 -- SEO topic research...")
        used  = _load_used_topics()
        topic = content_generator.research_seo_topic(used_topics=used)
        _log(f"  SEO topic: {topic}")

        # 2 -- Generate script and metadata
        _log("Step 2/6 -- Generating script and metadata...")
        package = content_generator.generate_video_package(used_topics=used, seo_topic=topic)
        _log(f"  Title    : {package[\'title\']}")
        _log(f"  Topic    : {package[\'topic\']}")
        _log(f"  Playlist : {package.get(\'playlist\', \'n/a\')}")

        # 3 -- Create thumbnail
        _log("Step 3/6 -- Creating thumbnail...")
        thumb_generator.generate_thumbnail(package["title"], thumb_path)

        # 4 -- Generate main video (Pictory)
        _log("Step 4/6 -- Generating main video (Pictory)...")
        video_generator.generate_video(
            title=package["title"],
            script=package["script"],
            scenes=package.get("scenes"),
            output_path=raw_path,
        )

        # 4b -- Avatar intro (HeyGen)
        _log("Step 4b/6 -- Generating avatar intro (HeyGen)...")
        intro = avatar_generator.generate_intro_clip(
            video_title=package["title"],
            photo_path=config.PRESENTER_PHOTO,
            output_path=intro_path,
        )

        # 4c -- Stitch
        if intro:
            _log("Step 4c/6 -- Stitching intro onto main video...")
            try:
                video_stitcher.splice_intro(intro_path, raw_path, video_path)
                _log("  Intro stitched successfully")
            except Exception as e:
                _log(f"  Stitch failed (non-fatal): {e}")
                os.rename(raw_path, video_path)
        else:
            _log("  No intro -- using raw Pictory video")
            os.rename(raw_path, video_path)

        # 5 -- Upload main video + thumbnail + playlist
        _log("Step 5/6 -- Uploading main video...")
        service = youtube_uploader._get_authenticated_service()
        url, video_id = youtube_uploader.upload_video(
            video_path=video_path,
            title=package["title"],
            description=package["description"],
            tags=package["tags"],
            service=service,
        )
        _log(f"  Main video live -> {url}")
        youtube_uploader.upload_thumbnail(service, video_id, thumb_path)

        playlist_name = package.get("playlist")
        if playlist_name:
            youtube_uploader.add_to_playlist(service, video_id, playlist_name)

        # Notify immediately when main video is live
        avatar_line = " | Avatar: ON" if intro else ""
        _notify(
            f"\\U0001f4f9 <b>{config.CHANNEL_NAME}</b> — New video live!\\n"
            f"\\U0001f3ac <a href=\\"{url}\\">{package[\'title\']}</a>{avatar_line}\\n"
            f"\\U0001f4cb Playlist: {playlist_name or \'None\'}"
        )

        # 5b -- Post channel comment with links to related videos
        _log("  Posting channel comment with related video links...")
        recent = youtube_uploader.get_recent_videos(service, exclude_id=video_id, max_results=3)
        youtube_uploader.post_channel_comment(service, video_id, recent)

        # 5c -- Update older video descriptions with link to this new video
        _log("  Updating older video descriptions with link to new video...")
        youtube_uploader.update_older_descriptions(service, package["title"], url, max_videos=3)

        _save_used_topic(package["topic"])

        # 6 -- 2 Shorts
        _log("Step 6/6 -- Generating and uploading Shorts (2 angles)...")
        for angle, suffix in [("stat", "a"), ("mistake", "b")]:
            short_url, short_title = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                # Notify immediately for each Short
                _notify(
                    f"\\U0001f3a6 <b>{config.CHANNEL_NAME}</b> — New Short live!\\n"
                    f"\\u26a1 <a href=\\"{short_url}\\">{short_title}</a>\\n"
                    f"\\U0001f517 Main video: <a href=\\"{url}\\">Watch</a>"
                )

        _log(f"SUCCESS -- {url}")

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify(
            f"\\u274c <b>{config.CHANNEL_NAME}</b> pipeline failed\\n"
            f"Error: {exc}"
        )
        sys.exit(1)

    finally:
        _cleanup(raw_path, video_path, intro_path, thumb_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--rename",  action="store_true")
    parser.add_argument("--run",     action="store_true")
    args = parser.parse_args()

    if args.rename:
        youtube_uploader.rename_channel(config.CHANNEL_NAME)
    elif args.run:
        run_pipeline()
    else:
        parser.print_help()
'''

# ── 2. monitor.py — per-video view tracking ───────────────────────────────────
MONITOR_PY = '''\
"""
monitor.py
Per-minute YouTube monitor. Tracks:
  - Per-video view counts (regular videos + Shorts separately)
  - Channel-level subscribers and video count
Sends Telegram on any real change. Uses high-watermark for views/subs.
"""

import json
import os
import pickle
from datetime import datetime, timezone

import requests

CHANNELS = {
    "Smart Money Daily": {
        "id":    "UC9k4fEX_Kg5ncM1E5rEiE3A",
        "token": "youtube_token_ch1.json",
        "emoji": "\\U0001f4b0",
    },
    "AI Advantage Daily": {
        "id":    "UCwXkcGaQFoYcR64KuOYhgbA",
        "token": "youtube_token_ch2.json",
        "emoji": "\\U0001f916",
    },
}

STATE_FILE  = "view_counts.json"
MONITOR_LOG = "monitor.log"


def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _log(msg):
    line = f"[{_ts()}] {msg}"
    print(line)
    with open(MONITOR_LOG, "a") as f:
        f.write(line + "\\n")


def _notify(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.status_code != 200:
            _log(f"Telegram error: {r.status_code}")
    except Exception as exc:
        _log(f"Telegram exception: {exc}")


def _load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _fmt(n):
    return f"{n:,}"


def _get_service(channel_id, token_file):
    """Returns an authenticated YouTube service or None."""
    try:
        from google.auth.transport.requests import Request
        import googleapiclient.discovery

        if not os.path.exists(token_file):
            return None

        with open(token_file, "rb") as f:
            credentials = pickle.load(f)

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(token_file, "wb") as f:
                pickle.dump(credentials, f)

        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
    except Exception as exc:
        _log(f"Auth error for {channel_id}: {exc}")
        return None


def _get_channel_stats(service, channel_id):
    """Returns dict with views, subscribers, videos for the channel."""
    try:
        resp  = service.channels().list(part="statistics", id=channel_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        stats = items[0]["statistics"]
        return {
            "views":       int(stats.get("viewCount",       0)),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "videos":      int(stats.get("videoCount",      0)),
        }
    except Exception as exc:
        _log(f"Channel stats error {channel_id}: {exc}")
        return None


def _get_video_views(service, channel_id):
    """
    Returns a dict of {video_id: {title, views, is_short}} for all uploads.
    is_short is True when duration <= 60s.
    """
    try:
        # Get uploads playlist ID
        ch = service.channels().list(part="contentDetails", id=channel_id).execute()
        uploads_pl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Get all video IDs from uploads playlist
        video_ids = []
        page_token = None
        while True:
            kwargs = dict(part="snippet", playlistId=uploads_pl, maxResults=50)
            if page_token:
                kwargs["pageToken"] = page_token
            pl_resp = service.playlistItems().list(**kwargs).execute()
            for item in pl_resp.get("items", []):
                video_ids.append(item["snippet"]["resourceId"]["videoId"])
            page_token = pl_resp.get("nextPageToken")
            if not page_token:
                break

        if not video_ids:
            return {}

        # Batch fetch statistics + contentDetails (duration) for all videos
        result = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            vresp = service.videos().list(
                part="statistics,contentDetails,snippet",
                id=",".join(batch)
            ).execute()
            for item in vresp.get("items", []):
                vid      = item["id"]
                title    = item["snippet"]["title"]
                views    = int(item["statistics"].get("viewCount", 0))
                duration = item["contentDetails"].get("duration", "PT0S")
                # Parse ISO 8601 duration — Shorts are <= 60s
                import re
                m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
                if m:
                    h, mn, s = (int(x or 0) for x in m.groups())
                    total_sec = h*3600 + mn*60 + s
                else:
                    total_sec = 999
                is_short = total_sec <= 60
                result[vid] = {"title": title, "views": views, "is_short": is_short}

        return result

    except Exception as exc:
        _log(f"Video views error {channel_id}: {exc}")
        return {}


def main():
    os.chdir("/opt/yt-automation")
    _log("Monitor run started")

    state     = _load_state()
    new_state = {}
    all_changes = []

    for name, ch in CHANNELS.items():
        service = _get_service(ch["id"], ch["token"])
        if not service:
            if name in state:
                new_state[name] = state[name]
            continue

        ch_stats = _get_channel_stats(service, ch["id"])
        vid_views = _get_video_views(service, ch["id"])

        if ch_stats is None:
            if name in state:
                new_state[name] = state[name]
            continue

        old = state.get(name, {})
        old_subs = old.get("subscribers", 0)
        old_vids = old.get("videos",      0)
        old_vid_views = old.get("video_views", {})

        new_subs = ch_stats["subscribers"]
        new_vids = ch_stats["videos"]

        # High-watermark for subs
        saved_subs = max(new_subs, old_subs)

        # Save state
        new_state[name] = {
            "subscribers":  saved_subs,
            "videos":       new_vids,
            "video_views":  {},
            "last_checked": _ts(),
        }

        changes = []

        # ── Subscriber change
        if new_subs > old_subs:
            diff  = new_subs - old_subs
            label = "subscriber" if diff == 1 else "subscribers"
            changes.append(f"  \\U0001f4c8 <b>Subscribers:</b> {_fmt(new_subs)} (+{diff} {label})")
        elif new_subs < old_subs:
            diff  = old_subs - new_subs
            label = "subscriber" if diff == 1 else "subscribers"
            changes.append(f"  \\U0001f4c9 <b>Subscribers:</b> {_fmt(new_subs)} (-{diff} {label})")

        # ── Video count change
        if new_vids != old_vids:
            icon   = "\\U0001f7e2" if new_vids > old_vids else "\\U0001f534"
            action = "added" if new_vids > old_vids else "deleted"
            delta  = abs(new_vids - old_vids)
            changes.append(f"  {icon} <b>Videos:</b> {new_vids} ({delta} {action})")

        # ── Per-video view changes
        view_changes_regular = []
        view_changes_shorts  = []

        for vid_id, info in vid_views.items():
            old_v    = old_vid_views.get(vid_id, {}).get("views", 0)
            new_v    = info["views"]
            # High-watermark: only report genuine increases
            saved_v  = max(new_v, old_v)
            new_state[name]["video_views"][vid_id] = {
                "views":    saved_v,
                "title":    info["title"],
                "is_short": info["is_short"],
            }
            if new_v > old_v:
                delta = new_v - old_v
                entry = f"    +{_fmt(delta)} views \\u2192 {_fmt(new_v)} total \\u2014 <i>{info[\'title\'][:50]}</i>"
                if info["is_short"]:
                    view_changes_shorts.append(entry)
                else:
                    view_changes_regular.append(entry)

        if view_changes_regular:
            changes.append("  \\U0001f4fa <b>Video views:</b>")
            changes.extend(view_changes_regular)

        if view_changes_shorts:
            changes.append("  \\u26a1 <b>Shorts views:</b>")
            changes.extend(view_changes_shorts)

        total_views    = sum(v["views"] for v in new_state[name]["video_views"].values())
        shorts_views   = sum(v["views"] for v in new_state[name]["video_views"].values() if v["is_short"])
        regular_views  = total_views - shorts_views

        _log(
            f"  [{name}] subs={_fmt(new_subs)} ({new_subs-old_subs:+d})  "
            f"videos={new_vids} ({new_vids-old_vids:+d})  "
            f"views={_fmt(total_views)} (reg={_fmt(regular_views)}, shorts={_fmt(shorts_views)})"
        )

        if changes:
            all_changes.append({
                "name":    name,
                "emoji":   ch["emoji"],
                "changes": changes,
                "total_views":   total_views,
                "shorts_views":  shorts_views,
                "regular_views": regular_views,
                "subs":          saved_subs,
            })

    _save_state(new_state)

    if all_changes:
        now   = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
        lines = [f"\\U0001f4ca <b>Channel Update</b> \\u2014 {now}", ""]

        for ch in all_changes:
            lines.append(f"{ch[\'emoji\']} <b>{ch[\'name\']}</b>")
            lines.extend(ch["changes"])
            lines.append(
                f"  \\U0001f441 Views: {_fmt(ch[\'regular_views\'])} regular + "
                f"{_fmt(ch[\'shorts_views\'])} Shorts  |  "
                f"\\U0001f465 {_fmt(ch[\'subs\'])} subs"
            )
            lines.append("")

        _notify("\\n".join(lines))
        _log(f"Notification sent — {len(all_changes)} channel(s) changed")
    else:
        _log("No changes detected — no notification sent")

    _log("Monitor run complete")


if __name__ == "__main__":
    main()
'''

FILES = {
    "main.py":    MAIN_PY,
    "monitor.py": MONITOR_PY,
}


def syntax_ok(code, name):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        print(f"  OK  {name}")
        return True
    except py_compile.PyCompileError as e:
        print(f"  ERR {name}: {e}")
        return False
    finally:
        os.unlink(tmp)


def main():
    print("Syntax checks:")
    for name, code in FILES.items():
        if not syntax_ok(code, name):
            raise SystemExit("Fix syntax errors before deploying.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWD)
    sftp = client.open_sftp()

    print("\nUploading:")
    for name, code in FILES.items():
        with sftp.open(f"{REMOTE}/{name}", "w") as rf:
            rf.write(code)
        print(f"  uploaded {name}")

    sftp.close()

    print("\nRemote syntax checks:")
    for name in FILES:
        _, out, err = client.exec_command(
            f"cd {REMOTE} && python3 -c \"import py_compile; py_compile.compile('{name}', doraise=True)\" 2>&1"
        )
        result = (out.read() + err.read()).decode().strip()
        print(f"  {name}: {'OK' if not result else result}")

    # Reset state so monitor re-baselines with per-video data
    print("\nResetting monitor state...")
    client.exec_command("rm -f /opt/yt-automation/view_counts.json")
    print("  view_counts.json cleared (monitor will re-baseline on next run)")

    client.close()
    print("""
Done.

  main.py:
    - Sends Telegram immediately when main video goes live
    - Sends separate Telegram for each Short when it goes live
    - No more waiting until all 6 steps complete

  monitor.py:
    - Tracks views per-video (not just channel total)
    - Separates regular video views from Shorts views
    - High-watermark applied per video
    - Notification shows which specific video gained views
""")


if __name__ == "__main__":
    main()
