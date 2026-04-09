"""Deploy hourly YouTube view monitor to the droplet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=30)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
MONITOR_PY = '''\
"""
monitor.py
Hourly YouTube channel monitor.
Fetches view/subscriber counts for both channels.
Sends a Telegram notification ONLY if total views increased since last check.
Stores last known counts in view_counts.json.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

# ── Config (hardcoded — no channel env var needed, monitors both) ─────────────
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

STATE_FILE   = "view_counts.json"
MONITOR_LOG  = "monitor.log"
YT_API       = "https://www.googleapis.com/youtube/v3/channels"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _log(msg: str) -> None:
    line = f"[{_ts()}] {msg}"
    print(line)
    with open(MONITOR_LOG, "a") as f:
        f.write(line + "\\n")


def _notify(msg: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        _log("Telegram not configured — skipping notification")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        if r.status_code != 200:
            _log(f"Telegram error: {r.status_code} {r.text[:100]}")
    except Exception as exc:
        _log(f"Telegram exception: {exc}")


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── YouTube stats fetch ───────────────────────────────────────────────────────

def _get_channel_stats(channel_id: str, token_file: str) -> dict | None:
    """
    Fetches statistics for a channel using its OAuth token.
    Returns dict with viewCount, subscriberCount, videoCount or None on error.
    """
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

        service = googleapiclient.discovery.build(
            "youtube", "v3", credentials=credentials
        )
        resp = service.channels().list(
            part="statistics,snippet",
            id=channel_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            _log(f"No data returned for channel {channel_id}")
            return None

        stats = items[0].get("statistics", {})
        return {
            "views":       int(stats.get("viewCount", 0)),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "videos":      int(stats.get("videoCount", 0)),
        }

    except Exception as exc:
        _log(f"Error fetching stats for {channel_id}: {exc}")
        return None


# ── Format helpers ────────────────────────────────────────────────────────────

def _fmt(n: int) -> str:
    """Format number with commas: 1234567 -> 1,234,567"""
    return f"{n:,}"


def _delta(new: int, old: int) -> str:
    """Format delta with sign and colour emoji: +123 or -5"""
    diff = new - old
    if diff > 0:
        return f"+{_fmt(diff)}"
    elif diff < 0:
        return f"-{_fmt(abs(diff))}"
    return "0"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.chdir("/opt/yt-automation")
    _log("Monitor run started")

    state    = _load_state()
    new_state = {}
    updates  = []   # channels where views increased
    any_change = False

    for name, ch in CHANNELS.items():
        stats = _get_channel_stats(ch["id"], ch["token"])
        if stats is None:
            _log(f"  [{name}] Could not fetch stats — skipping")
            # Keep old state
            if name in state:
                new_state[name] = state[name]
            continue

        old = state.get(name, {})
        old_views = old.get("views", 0)
        old_subs  = old.get("subscribers", 0)

        new_views = stats["views"]
        new_subs  = stats["subscribers"]

        view_diff = new_views - old_views
        sub_diff  = new_subs  - old_subs

        _log(f"  [{name}] views={_fmt(new_views)} ({_delta(new_views, old_views)})  "
             f"subs={_fmt(new_subs)} ({_delta(new_subs, old_subs)})  "
             f"videos={stats['videos']}")

        new_state[name] = {
            "views":       new_views,
            "subscribers": new_subs,
            "videos":      stats["videos"],
            "last_checked": _ts(),
        }

        if view_diff > 0:
            any_change = True
            updates.append({
                "name":       name,
                "emoji":      ch["emoji"],
                "views":      new_views,
                "view_delta": view_diff,
                "subs":       new_subs,
                "sub_delta":  sub_diff,
                "videos":     stats["videos"],
            })

    _save_state(new_state)

    # Only notify if at least one channel gained views
    if any_change:
        now = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
        lines = [f"\U0001f4ca <b>Views Update</b> — {now}", ""]

        for u in updates:
            sub_line = ""
            if u["sub_delta"] > 0:
                sub_line = f"  \U0001f4c8 +{_fmt(u['sub_delta'])} new subscriber{'s' if u['sub_delta'] != 1 else ''}"
            elif u["sub_delta"] < 0:
                sub_line = f"  \U0001f4c9 {_fmt(u['sub_delta'])} subscriber{'s' if abs(u['sub_delta']) != 1 else ''}"

            lines += [
                f"{u['emoji']} <b>{u['name']}</b>",
                f"  \U0001f441 {_fmt(u['views'])} views  <b>(+{_fmt(u['view_delta'])})</b>",
            ]
            if sub_line:
                lines.append(sub_line)
            lines.append("")

        # Totals across both channels
        total_views = sum(new_state[n]["views"] for n in new_state)
        total_subs  = sum(new_state[n]["subscribers"] for n in new_state)
        lines += [
            "\U0001f30e <b>Combined</b>",
            f"  \U0001f441 {_fmt(total_views)} total views",
            f"  \U0001f465 {_fmt(total_subs)} total subscribers",
        ]

        msg = "\\n".join(lines)
        _notify(msg)
        _log(f"Telegram notification sent ({len(updates)} channel(s) with new views)")
    else:
        _log("No view increase detected — no notification sent")

    _log("Monitor run complete")


if __name__ == "__main__":
    main()
'''

# ─────────────────────────────────────────────────────────────────────────────
MONITOR_SH = '''\
#!/bin/bash
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python monitor.py
'''

# ── Upload ────────────────────────────────────────────────────────────────────
files = {
    "monitor.py": MONITOR_PY,
    "monitor.sh": MONITOR_SH,
}
for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

# Make executable + syntax check
stdin, stdout, stderr = client.exec_command("chmod +x /opt/yt-automation/monitor.sh")
stdout.read()

print("\nSyntax checks:")
for fname in ["monitor.py"]:
    stdin, stdout, stderr = client.exec_command(
        f"cd {BASE} && source venv/bin/activate && python -m py_compile {fname} && echo '{fname} OK'"
    )
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err)

# Add hourly cron (at minute 0 every hour)
stdin, stdout, stderr = client.exec_command("crontab -l")
current = stdout.read().decode().strip()
new_crontab = current + "\n0 * * * * /opt/yt-automation/monitor.sh\n"
stdin, stdout, stderr = client.exec_command(f'echo "{new_crontab.strip()}" | crontab -')
stdout.read()

print("\nUpdated crontab:")
stdin, stdout, stderr = client.exec_command("crontab -l")
print(stdout.read().decode().strip())

# Run it once now to seed the state file and test
print("\nRunning monitor now to seed initial state...")
stdin, stdout, stderr = client.exec_command(
    "cd /opt/yt-automation && set -a && source .env && set +a && source venv/bin/activate && python monitor.py 2>&1",
    timeout=30
)
import time; time.sleep(25)
out = stdout.read().decode(errors="replace")
print(out)

client.close()
print("Done.")
