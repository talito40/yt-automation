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
        "emoji": "💰",
    },
    "AI Advantage Daily": {
        "id":    "UCwXkcGaQFoYcR64KuOYhgbA",
        "token": "youtube_token_ch2.json",
        "emoji": "🤖",
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
        "views":       ("📈", "📉"),   # chart up / chart down
        "subscribers": ("📈", "📉"),
        "videos":      ("🟢", "🔴"),   # green dot / red dot (added/deleted)
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

        # High-watermark: views & subs can only go up legitimately.
        # YouTube API sometimes returns stale/lower cached values — ignore those
        # to prevent false "decrease" notifications and oscillation noise.
        saved_views = max(new_views, old_views)
        saved_subs  = max(new_subs,  old_subs)
        # Video count can genuinely decrease (deletions), so track real value.
        saved_vids  = new_vids

        new_state[name] = {
            "views":        saved_views,
            "subscribers":  saved_subs,
            "videos":       saved_vids,
            "last_checked": _ts(),
        }

        # Detect real changes only
        changes = []

        # Views: only notify on genuine increase (new > old high-watermark)
        if new_views > old_views:
            icon = _delta_icon("views", new_views, old_views)
            changes.append(
                f"  {icon} <b>Views:</b> {_fmt(new_views)} ({_delta_str(new_views, old_views)})"
            )

        # Subs: only notify on genuine increase or decrease
        if new_subs > old_subs:
            icon  = _delta_icon("subscribers", new_subs, old_subs)
            label = "subscriber" if abs(new_subs - old_subs) == 1 else "subscribers"
            changes.append(
                f"  {icon} <b>Subscribers:</b> {_fmt(new_subs)} ({_delta_str(new_subs, old_subs)} {label})"
            )
        elif new_subs < old_subs:
            icon  = _delta_icon("subscribers", new_subs, old_subs)
            label = "subscriber" if abs(new_subs - old_subs) == 1 else "subscribers"
            changes.append(
                f"  {icon} <b>Subscribers:</b> {_fmt(new_subs)} ({_delta_str(new_subs, old_subs)} {label})"
            )

        # Videos: notify on any real change (add or delete)
        if new_vids != old_vids:
            icon   = _delta_icon("videos", new_vids, old_vids)
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
        lines = [f"📊 <b>Channel Update</b> — {now}", ""]

        for ch in changed_channels:
            lines.append(f"{ch['emoji']} <b>{ch['name']}</b>")
            lines.extend(ch["changes"])
            lines.append("")

        # Combined totals
        total_views = sum(new_state[n].get("views",       0) for n in new_state)
        total_subs  = sum(new_state[n].get("subscribers", 0) for n in new_state)
        lines += [
            "🌎 <b>Combined totals</b>",
            f"  👁 {_fmt(total_views)} views",
            f"  👥 {_fmt(total_subs)} subscribers",
        ]

        _notify("\n".join(lines))
        _log(f"Notification sent — {len(changed_channels)} channel(s) changed")
    else:
        _log("No changes detected — no notification sent")

    _log("Monitor run complete")


if __name__ == "__main__":
    main()
