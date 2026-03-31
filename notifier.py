"""
notifier.py
Sends Telegram notifications via a bot.

Required env vars:
  TELEGRAM_BOT_TOKEN — bot token from @BotFather
  TELEGRAM_CHAT_ID   — chat ID to send messages to
"""

import os
import time
import requests
from datetime import datetime, timezone


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[notifier] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
            resp.raise_for_status()
            print(f"[notifier] Telegram message sent.")
            return
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                print(f"[notifier] Failed after 3 attempts: {e}")
                return
            wait = attempt * 5
            print(f"[notifier] Attempt {attempt} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)


def send_upload_success(channel_name: str, title: str, url: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _send(
        f"✅ Video uploaded!\n\n"
        f"Channel: {channel_name}\n"
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Time: {now}"
    )


def send_quota_warning(used: int, total: int, remaining: int) -> None:
    _send(
        f"⚠️ Pictory quota low!\n\n"
        f"Used: {used}/{total}\n"
        f"Remaining: {remaining} renders\n\n"
        f"Top up your Pictory plan to avoid pipeline failures."
    )


def send_test(channel_name: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _send(
        f"🤖 Test notification\n\n"
        f"Channel: {channel_name}\n"
        f"Time: {now}\n\n"
        f"Notifications are working!"
    )

