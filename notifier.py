"""
notifier.py
Sends email notifications via Gmail SMTP.

Required env vars:
  NOTIFY_EMAIL        — Gmail address to send FROM (e.g. yourbot@gmail.com)
  NOTIFY_APP_PASSWORD — Gmail App Password (16-char, spaces optional)
  NOTIFY_TO           — Recipient address (lukaki.store@gmail.com)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

NOTIFY_FROM = os.environ.get("NOTIFY_EMAIL", "")
NOTIFY_PASS = os.environ.get("NOTIFY_APP_PASSWORD", "").replace(" ", "")
NOTIFY_TO   = os.environ.get("NOTIFY_TO", "lukaki.store@gmail.com")


def _send(subject: str, body: str) -> None:
    if not NOTIFY_FROM or not NOTIFY_PASS:
        print("[notifier] NOTIFY_EMAIL or NOTIFY_APP_PASSWORD not set — skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = NOTIFY_FROM
    msg["To"]      = NOTIFY_TO
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(NOTIFY_FROM, NOTIFY_PASS)
        server.sendmail(NOTIFY_FROM, NOTIFY_TO, msg.as_string())

    print(f"[notifier] Email sent to {NOTIFY_TO}: {subject}")


def send_upload_success(channel_name: str, title: str, url: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[{channel_name}] Video uploaded — {title}"
    body = (
        f"Your daily video was uploaded successfully.\n\n"
        f"Channel : {channel_name}\n"
        f"Title   : {title}\n"
        f"URL     : {url}\n"
        f"Time    : {now}\n"
    )
    _send(subject, body)


def send_test(channel_name: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[{channel_name}] Test notification"
    body = (
        f"This is a test email from your YouTube automation pipeline.\n\n"
        f"Channel : {channel_name}\n"
        f"Time    : {now}\n\n"
        f"If you received this, email notifications are working correctly."
    )
    _send(subject, body)
