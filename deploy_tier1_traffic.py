"""Deploy Tier 1 traffic features + monitor fix."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=30)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
# 1. youtube_uploader.py — add comment posting + internal link updating
# ─────────────────────────────────────────────────────────────────────────────
YOUTUBE_UPLOADER = '''\
"""
youtube_uploader.py
Handles all YouTube Data API v3 operations including playlists,
comments, and internal description linking.
"""

import json
import os
import pickle
import time
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
from google.auth.transport.requests import Request
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CATEGORY_ID = "27"
PRIVACY     = "public"
_PLAYLIST_CACHE_FILE = lambda: f"playlists_ch{config.CHANNEL}.json"


def _get_authenticated_service():
    credentials = None
    if os.path.exists(config.YOUTUBE_TOKEN_FILE):
        with open(config.YOUTUBE_TOKEN_FILE, "rb") as f:
            credentials = pickle.load(f)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS, SCOPES
            )
            credentials = flow.run_local_server(port=0)
        with open(config.YOUTUBE_TOKEN_FILE, "wb") as f:
            pickle.dump(credentials, f)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def _do_upload(service, body: dict, video_path: str) -> tuple[str, str]:
    media    = googleapiclient.http.MediaFileUpload(
        video_path, mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 10,
    )
    request  = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry    = 0
    while response is None:
        try:
            print(f"[youtube] Uploading... (attempt {retry + 1})")
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] Upload progress: {int(status.progress() * 100)}%")
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < config.MAX_RETRIES:
                retry += 1
                time.sleep(5 * retry)
            else:
                raise
    video_id = response["id"]
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def upload_video(video_path, title, description, tags, service=None):
    if service is None:
        service = _get_authenticated_service()
    body = {
        "snippet": {
            "title": title[:100], "description": description[:5000],
            "tags": tags[:500], "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Upload complete -> {url}")
    return url, video_id


def upload_short(video_path, title, description, tags, service=None):
    if service is None:
        service = _get_authenticated_service()
    short_title = title if "#Shorts" in title else f"{title} #Shorts"
    short_desc  = f"{description}\\n\\n#Shorts #YouTubeShorts"
    short_tags  = list(dict.fromkeys((tags or []) + ["Shorts", "YouTubeShorts"]))
    body = {
        "snippet": {
            "title": short_title[:100], "description": short_desc[:5000],
            "tags": short_tags, "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Short uploaded -> {url}")
    return url, video_id


def upload_thumbnail(service, video_id, thumbnail_path):
    try:
        service.thumbnails().set(
            videoId=video_id,
            media_body=googleapiclient.http.MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        ).execute()
        print(f"[youtube] Thumbnail set for {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Thumbnail skipped (channel not verified): {e.reason}")
        return False


# ── Playlist management ───────────────────────────────────────────────────────

def _load_playlist_cache():
    f = _PLAYLIST_CACHE_FILE()
    if os.path.exists(f):
        with open(f) as fh:
            return json.load(fh)
    return {}


def _save_playlist_cache(cache):
    with open(_PLAYLIST_CACHE_FILE(), "w") as f:
        json.dump(cache, f, indent=2)


def get_or_create_playlist(service, playlist_name):
    cache = _load_playlist_cache()
    if playlist_name in cache:
        return cache[playlist_name]
    response = service.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": playlist_name,
                "description": f"{playlist_name} | {config.CHANNEL_NAME}",
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    playlist_id = response["id"]
    cache[playlist_name] = playlist_id
    _save_playlist_cache(cache)
    print(f"[youtube] Created playlist \'{playlist_name}\' -> {playlist_id}")
    return playlist_id


def add_to_playlist(service, video_id, playlist_name):
    try:
        playlist_id = get_or_create_playlist(service, playlist_name)
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"[youtube] Added {video_id} to playlist \'{playlist_name}\'")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Playlist add failed (non-fatal): {e.reason}")
        return False


# ── Recent videos ─────────────────────────────────────────────────────────────

def get_recent_videos(service, exclude_id: str = "", max_results: int = 3) -> list[dict]:
    """
    Returns list of {title, url, video_id, description} for the channel\'s
    most recent public videos, excluding exclude_id.
    """
    try:
        # The uploads playlist ID = channel ID with UC -> UU prefix
        uploads_playlist = "UU" + config.YOUTUBE_CHANNEL_ID[2:]
        resp = service.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist,
            maxResults=max_results + 1,
        ).execute()
        videos = []
        for item in resp.get("items", []):
            vid_id = item["snippet"]["resourceId"]["videoId"]
            if vid_id == exclude_id:
                continue
            videos.append({
                "video_id":    vid_id,
                "title":       item["snippet"]["title"],
                "url":         f"https://www.youtube.com/watch?v={vid_id}",
                "description": item["snippet"].get("description", ""),
            })
            if len(videos) >= max_results:
                break
        return videos
    except Exception as e:
        print(f"[youtube] Could not fetch recent videos (non-fatal): {e}")
        return []


# ── Auto comment ──────────────────────────────────────────────────────────────

def post_channel_comment(service, video_id: str, recent_videos: list[dict]) -> bool:
    """
    Posts a first comment on the video with links to related recent videos.
    Channel owner comments are displayed prominently by YouTube.
    """
    if not recent_videos:
        print("[youtube] No recent videos to link — skipping comment")
        return False
    try:
        lines = [f"\U0001f447 More videos you\'ll love:"]
        for v in recent_videos[:3]:
            lines.append(f"\u2022 {v[\'title\']} \u2192 {v[\'url\']}")
        lines += [
            "",
            f"\U0001f514 Subscribe for daily {config.NICHE} tips!",
        ]
        comment_text = "\\n".join(lines)

        service.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    },
                }
            },
        ).execute()
        print(f"[youtube] Comment posted on {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Comment post failed (non-fatal): {e.reason}")
        return False


# ── Internal linking ──────────────────────────────────────────────────────────

def update_older_descriptions(service, new_title: str, new_url: str, max_videos: int = 3) -> None:
    """
    Appends a \'New video\' link to the descriptions of the last N older videos.
    Only adds the link if it\'s not already there (idempotent).
    """
    older = get_recent_videos(service, exclude_id="", max_results=max_videos + 1)
    link_line = f"\\n\U0001f195 New: {new_title} \u2192 {new_url}"

    for v in older[:max_videos]:
        try:
            # Fetch full snippet
            resp = service.videos().list(
                part="snippet", id=v["video_id"]
            ).execute()
            items = resp.get("items", [])
            if not items:
                continue
            snippet = items[0]["snippet"]
            current_desc = snippet.get("description", "")

            # Skip if already linked
            if new_url in current_desc:
                continue

            new_desc = current_desc + link_line
            snippet["description"] = new_desc[:5000]

            service.videos().update(
                part="snippet",
                body={"id": v["video_id"], "snippet": snippet},
            ).execute()
            print(f"[youtube] Updated description of \'{v[\'title\']}\' with link to new video")
        except googleapiclient.errors.HttpError as e:
            print(f"[youtube] Description update failed for {v[\'video_id\']} (non-fatal): {e.reason}")


def rename_channel(new_name):
    service = _get_authenticated_service()
    service.channels().update(
        part="snippet",
        body={"id": config.YOUTUBE_CHANNEL_ID, "snippet": {"title": new_name}},
    ).execute()
    print(f"[youtube] Channel renamed to \'{new_name}\'")
'''

# ─────────────────────────────────────────────────────────────────────────────
# 2. content_generator.py — add hashtags to descriptions
# ─────────────────────────────────────────────────────────────────────────────
# Read existing file and patch just the generate_video_package prompt
# to include hashtags in the description output

# ─────────────────────────────────────────────────────────────────────────────
# 3. main.py — wire in comment + internal linking after upload
# ─────────────────────────────────────────────────────────────────────────────
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


def _notify_telegram(msg):
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
        shorts_pkg["description"] = shorts_pkg["description"].replace("[MAIN_VIDEO_URL]", main_url)
        video_generator.generate_shorts_video(
            title=shorts_pkg["title"],
            script=shorts_pkg["script"],
            scenes=shorts_pkg.get("scenes"),
            output_path=short_path,
        )
        short_url, _ = youtube_uploader.upload_short(
            video_path=short_path,
            title=shorts_pkg["title"],
            description=shorts_pkg["description"],
            tags=shorts_pkg.get("tags", []),
            service=service,
        )
        return short_url
    except Exception as exc:
        _log(f"  Short ({angle}) failed (non-fatal): {exc}")
        return None
    finally:
        _cleanup(short_path)


def run_pipeline():
    today      = date.today().isoformat()
    raw_path   = f"video_raw_{today}.mp4"
    video_path = f"video_{today}.mp4"
    intro_path = f"intro_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"
    short_urls = []

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
            short_url = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                short_urls.append(short_url)

        _log(f"SUCCESS -- {url}")

        shorts_text = ""
        for i, su in enumerate(short_urls, 1):
            shorts_text += f"\\n\U0001f3a5 Short {i}: <a href=\\"{su}\\">Watch</a>"
        avatar_line = "\\n\U0001f916 Avatar intro: ON" if intro else "\\n\U0001f916 Avatar intro: OFF"
        _notify_telegram(
            f"\u2705 <b>{config.CHANNEL_NAME}</b>\\n"
            f"\U0001f4f9 <a href=\\"{url}\\">{package[\'title\']}</a>"
            + avatar_line + shorts_text
        )

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify_telegram(
            f"\u274c <b>{config.CHANNEL_NAME}</b> pipeline failed\\n"
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

# ─────────────────────────────────────────────────────────────────────────────
# 4. monitor.py — notify on ANY change (views, subs, video count)
# ─────────────────────────────────────────────────────────────────────────────
MONITOR_PY = '''\
"""
monitor.py
Hourly YouTube channel monitor.
Sends a Telegram notification if ANY metric changes:
  - views up or down
  - subscribers up or down
  - video count up or down (catches deletions too)
"""

import json
import os
from datetime import datetime, timezone

import requests

CHANNELS = {
    "Smart Money Daily": {
        "id":    "UC9k4fEX_Kg5ncM1E5rEiE3A",
        "token": "youtube_token_ch1.json",
        "emoji": "\U0001f4b0",
    },
    "AI Advantage Daily": {
        "id":    "UCwXkcGaQFoYcR64KuOYhgbA",
        "token": "youtube_token_ch2.json",
        "emoji": "\U0001f916",
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


def _delta_str(new, old):
    d = new - old
    if d > 0: return f"+{_fmt(d)}"
    if d < 0: return f"-{_fmt(abs(d))}"
    return "0"


def _delta_icon(metric, new, old):
    """Return appropriate emoji based on metric and direction."""
    d = new - old
    if d == 0:
        return ""
    icons = {
        "views":       ("\U0001f4c8", "\U0001f4c9"),   # chart up / chart down
        "subscribers": ("\U0001f4c8", "\U0001f4c9"),
        "videos":      ("\U0001f7e2", "\U0001f534"),   # green dot / red dot (added/deleted)
    }
    up_icon, down_icon = icons.get(metric, ("+", "-"))
    return up_icon if d > 0 else down_icon


def _get_channel_stats(channel_id, token_file):
    try:
        import pickle
        from google.auth.transport.requests import Request
        import googleapiclient.discovery

        if not os.path.exists(token_file):
            _log(f"Token file not found: {token_file}")
            return None

        with open(token_file, "rb") as f:
            credentials = pickle.load(f)

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(token_file, "wb") as f:
                pickle.dump(credentials, f)

        service = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)
        resp    = service.channels().list(
            part="statistics", id=channel_id,
        ).execute()

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
        _log(f"Error fetching stats for {channel_id}: {exc}")
        return None


def main():
    os.chdir("/opt/yt-automation")
    _log("Monitor run started")

    state     = _load_state()
    new_state = {}
    changed_channels = []

    for name, ch in CHANNELS.items():
        stats = _get_channel_stats(ch["id"], ch["token"])
        if stats is None:
            if name in state:
                new_state[name] = state[name]
            continue

        old = state.get(name, {})
        old_views = old.get("views",       0)
        old_subs  = old.get("subscribers", 0)
        old_vids  = old.get("videos",      0)

        new_views = stats["views"]
        new_subs  = stats["subscribers"]
        new_vids  = stats["videos"]

        _log(
            f"  [{name}] "
            f"views={_fmt(new_views)} ({_delta_str(new_views, old_views)})  "
            f"subs={_fmt(new_subs)} ({_delta_str(new_subs, old_subs)})  "
            f"videos={new_vids} ({_delta_str(new_vids, old_vids)})"
        )

        new_state[name] = {
            "views":        new_views,
            "subscribers":  new_subs,
            "videos":       new_vids,
            "last_checked": _ts(),
        }

        # Detect any change across all metrics
        changes = []

        if new_views != old_views:
            icon = _delta_icon("views", new_views, old_views)
            changes.append(
                f"  {icon} <b>Views:</b> {_fmt(new_views)} ({_delta_str(new_views, old_views)})"
            )

        if new_subs != old_subs:
            icon = _delta_icon("subscribers", new_subs, old_subs)
            label = "subscriber" if abs(new_subs - old_subs) == 1 else "subscribers"
            changes.append(
                f"  {icon} <b>Subscribers:</b> {_fmt(new_subs)} ({_delta_str(new_subs, old_subs)} {label})"
            )

        if new_vids != old_vids:
            icon  = _delta_icon("videos", new_vids, old_vids)
            action = "video added" if new_vids > old_vids else "video deleted"
            changes.append(
                f"  {icon} <b>Videos:</b> {new_vids} ({_delta_str(new_vids, old_vids)} {action})"
            )

        if changes:
            changed_channels.append({
                "name":    name,
                "emoji":   ch["emoji"],
                "changes": changes,
                "stats":   new_state[name],
            })

    _save_state(new_state)

    if changed_channels:
        now   = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
        lines = [f"\U0001f4ca <b>Channel Update</b> — {now}", ""]

        for ch in changed_channels:
            lines.append(f"{ch[\'emoji\']} <b>{ch[\'name\']}</b>")
            lines.extend(ch["changes"])
            lines.append("")

        # Combined totals
        total_views = sum(new_state[n].get("views",       0) for n in new_state)
        total_subs  = sum(new_state[n].get("subscribers", 0) for n in new_state)
        lines += [
            "\U0001f30e <b>Combined totals</b>",
            f"  \U0001f441 {_fmt(total_views)} views",
            f"  \U0001f465 {_fmt(total_subs)} subscribers",
        ]

        _notify("\\n".join(lines))
        _log(f"Notification sent — {len(changed_channels)} channel(s) changed")
    else:
        _log("No changes detected — no notification sent")

    _log("Monitor run complete")


if __name__ == "__main__":
    main()
'''

# ─────────────────────────────────────────────────────────────────────────────
# content_generator.py — patch: add hashtags to description
# ─────────────────────────────────────────────────────────────────────────────
# Read current file, inject hashtag instruction into the prompt
stdin, stdout, stderr = client.exec_command(f'cat {BASE}/content_generator.py')
cg_content = stdout.read().decode(errors='replace')

OLD_DESC_RULE = '- Description: 3 paragraphs -- summary (with SEO keywords), affiliate CTA'
NEW_DESC_RULE = ('- Description: 3 paragraphs -- summary (with SEO keywords), affiliate CTA. '
                 'End the description with 5 relevant hashtags (e.g. #PersonalFinance #InvestingTips)')
cg_patched = cg_content.replace(OLD_DESC_RULE, NEW_DESC_RULE)

# ── Upload all files ──────────────────────────────────────────────────────────
files = {
    "youtube_uploader.py":  YOUTUBE_UPLOADER,
    "main.py":              MAIN_PY,
    "monitor.py":           MONITOR_PY,
}
for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

# Write patched content_generator
with sftp.open(f"{BASE}/content_generator.py", "w") as f:
    f.write(cg_patched)
print("  patched  content_generator.py (hashtags added)")

sftp.close()

# Syntax checks
print("\nSyntax checks:")
for fname in ["youtube_uploader.py", "main.py", "monitor.py", "content_generator.py"]:
    stdin, stdout, stderr = client.exec_command(
        f"cd {BASE} && source venv/bin/activate && python -m py_compile {fname} && echo '{fname} OK'"
    )
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err)

# Run monitor now so user sees it working
print("\nRunning monitor now...")
import time
stdin, stdout, stderr = client.exec_command(
    f"cd {BASE} && set -a && source .env && set +a && source venv/bin/activate && python monitor.py 2>&1"
)
time.sleep(25)
out = stdout.read().decode(errors="replace")
print(out)

client.close()
print("Done.")
