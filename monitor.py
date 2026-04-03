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
        f.write(line + "\n")


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
            changes.append(f"  \U0001f4c8 <b>Subscribers:</b> {_fmt(new_subs)} (+{diff} {label})")
        elif new_subs < old_subs:
            diff  = old_subs - new_subs
            label = "subscriber" if diff == 1 else "subscribers"
            changes.append(f"  \U0001f4c9 <b>Subscribers:</b> {_fmt(new_subs)} (-{diff} {label})")

        # ── Video count change
        if new_vids != old_vids:
            icon   = "\U0001f7e2" if new_vids > old_vids else "\U0001f534"
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
                entry = f"    +{_fmt(delta)} views \u2192 {_fmt(new_v)} total \u2014 <i>{info['title'][:50]}</i>"
                if info["is_short"]:
                    view_changes_shorts.append(entry)
                else:
                    view_changes_regular.append(entry)

        if view_changes_regular:
            changes.append("  \U0001f4fa <b>Video views:</b>")
            changes.extend(view_changes_regular)

        if view_changes_shorts:
            changes.append("  \u26a1 <b>Shorts views:</b>")
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
        lines = [f"\U0001f4ca <b>Channel Update</b> \u2014 {now}", ""]

        for ch in all_changes:
            lines.append(f"{ch['emoji']} <b>{ch['name']}</b>")
            lines.extend(ch["changes"])
            lines.append(
                f"  \U0001f441 Views: {_fmt(ch['regular_views'])} regular + "
                f"{_fmt(ch['shorts_views'])} Shorts  |  "
                f"\U0001f465 {_fmt(ch['subs'])} subs"
            )
            lines.append("")

        _notify("\n".join(lines))
        _log(f"Notification sent — {len(all_changes)} channel(s) changed")
    else:
        _log("No changes detected — no notification sent")

    _log("Monitor run complete")


if __name__ == "__main__":
    main()
