"""Deploy HeyGen avatar integration to the droplet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
# avatar_generator.py
# Calls HeyGen API to generate a 12-second talking-head intro clip.
# Flow:
#   1. Upload presenter photo -> get talking_photo_id (cached per channel)
#   2. Generate video (photo + intro script) -> get video_id
#   3. Poll until complete -> download MP4
# ─────────────────────────────────────────────────────────────────────────────
AVATAR_GENERATOR = '''\
"""
avatar_generator.py
Generates a short talking-head intro clip via HeyGen API.
The presenter photo is uploaded once and the ID cached per channel.
"""

import json
import os
import time
import requests
import config

HEYGEN_BASE = "https://api.heygen.com"
_CACHE_FILE = lambda: f"heygen_avatar_ch{config.CHANNEL}.json"


def _headers() -> dict:
    return {
        "X-Api-Key": config.HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Talking photo ID (upload once, cache forever) ─────────────────────────────

def _load_cache() -> dict:
    f = _CACHE_FILE()
    if os.path.exists(f):
        with open(f) as fh:
            return json.load(fh)
    return {}


def _save_cache(data: dict) -> None:
    with open(_CACHE_FILE(), "w") as f:
        json.dump(data, f, indent=2)


def _get_talking_photo_id(photo_path: str) -> str:
    """
    Uploads the presenter photo to HeyGen and returns its talking_photo_id.
    Result is cached in heygen_avatar_ch{N}.json so we only upload once.
    """
    cache = _load_cache()
    if cache.get("talking_photo_id"):
        print(f"[avatar] Using cached talking_photo_id: {cache['talking_photo_id']}")
        return cache["talking_photo_id"]

    print(f"[avatar] Uploading presenter photo: {photo_path}")
    with open(photo_path, "rb") as f:
        image_data = f.read()

    # Step 1: get upload URL
    resp = requests.post(
        f"{HEYGEN_BASE}/v1/talking_photo",
        headers={
            "X-Api-Key": config.HEYGEN_API_KEY,
            "Content-Type": "image/jpeg",
        },
        data=image_data,
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    talking_photo_id = result.get("data", {}).get("talking_photo_id") or result.get("talking_photo_id")
    if not talking_photo_id:
        raise RuntimeError(f"HeyGen photo upload failed: {result}")

    cache["talking_photo_id"] = talking_photo_id
    _save_cache(cache)
    print(f"[avatar] Photo uploaded, talking_photo_id={talking_photo_id}")
    return talking_photo_id


# ── Video generation ──────────────────────────────────────────────────────────

def _build_intro_script(video_title: str) -> str:
    """
    Creates a punchy 12-15 second spoken intro from the video title.
    Kept short to minimise API cost (~$0.20-0.25 per clip).
    """
    # Strip trailing punctuation from title for natural delivery
    title = video_title.rstrip(".!?")
    return (
        f"Hey, welcome back. Today we are breaking down {title}. "
        f"Stay with me — this one is going to save you a lot of money and time. Let's get into it."
    )


def generate_intro_clip(
    video_title: str,
    photo_path: str,
    output_path: str = "intro.mp4",
) -> str | None:
    """
    Generates a ~15-second talking-head intro clip using HeyGen.
    Returns the absolute path to the downloaded MP4, or None if disabled/failed.
    """
    if not config.HEYGEN_API_KEY:
        print("[avatar] HEYGEN_API_KEY not set — skipping avatar intro")
        return None

    if not os.path.exists(photo_path):
        print(f"[avatar] Presenter photo not found at {photo_path} — skipping avatar intro")
        return None

    try:
        talking_photo_id = _get_talking_photo_id(photo_path)
        intro_text       = _build_intro_script(video_title)

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "talking_photo",
                        "talking_photo_id": talking_photo_id,
                    },
                    "voice": {
                        "type": "text",
                        "input_text": intro_text,
                        "voice_id": config.HEYGEN_VOICE_ID,
                    },
                    "background": {
                        "type": "color",
                        "value": config.HEYGEN_BG_COLOR,
                    },
                }
            ],
            "dimension": {"width": 1920, "height": 1080},
            "aspect_ratio": "16:9",
        }

        resp = requests.post(
            f"{HEYGEN_BASE}/v2/video/generate",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result   = resp.json()
        video_id = result.get("data", {}).get("video_id") or result.get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen video generate failed: {result}")

        print(f"[avatar] Rendering intro, video_id={video_id}")
        video_url = _poll_until_ready(video_id)
        abs_path  = _download(video_url, output_path)
        return abs_path

    except Exception as exc:
        print(f"[avatar] Intro generation failed (non-fatal): {exc}")
        return None


def _poll_until_ready(video_id: str, max_wait: int = 300) -> str:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(
            f"{HEYGEN_BASE}/v1/video_status.get?video_id={video_id}",
            headers=_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        data   = resp.json().get("data", {})
        status = data.get("status", "").lower()
        print(f"[avatar] Status: {status}")

        if status == "completed":
            url = data.get("video_url")
            if not url:
                raise RuntimeError("HeyGen completed but no video_url returned")
            return url
        if status in ("failed", "error"):
            raise RuntimeError(f"HeyGen render failed: {data}")

        time.sleep(8)

    raise TimeoutError("HeyGen render timed out after 5 minutes")


def _download(url: str, output_path: str) -> str:
    abs_path = os.path.abspath(output_path)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(abs_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    print(f"[avatar] Downloaded intro -> {abs_path} ({size_mb:.1f} MB)")
    return abs_path
'''

# ─────────────────────────────────────────────────────────────────────────────
# video_stitcher.py
# Uses ffmpeg to concatenate intro clip + main video seamlessly.
# Also handles the case where no intro exists (passthrough).
# ─────────────────────────────────────────────────────────────────────────────
VIDEO_STITCHER = '''\
"""
video_stitcher.py
Splices an avatar intro clip onto the front of the main video using ffmpeg.
Both clips must be 1920x1080 MP4s (H.264/AAC) for seamless concat.
"""

import os
import subprocess
import tempfile


def splice_intro(intro_path: str, main_path: str, output_path: str) -> str:
    """
    Concatenates intro_path + main_path -> output_path.
    Re-encodes both to ensure identical stream parameters before joining.
    Returns absolute path to the stitched video.
    """
    abs_out = os.path.abspath(output_path)

    # Write a concat list file
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        tmp.write(f"file \'{os.path.abspath(intro_path)}\'\\n")
        tmp.write(f"file \'{os.path.abspath(main_path)}\'\\n")
        list_path = tmp.name

    try:
        # Re-encode both clips to a common profile then concat
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            abs_out,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\\n{result.stderr[-1000:]}")

        size_mb = os.path.getsize(abs_out) / (1024 * 1024)
        print(f"[stitch] Stitched video -> {abs_out} ({size_mb:.1f} MB)")
        return abs_out

    finally:
        os.unlink(list_path)
'''

# ─────────────────────────────────────────────────────────────────────────────
# config.py — add HeyGen settings
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PY = '''\
import os

CHANNEL = int(os.environ.get("CHANNEL", "1"))

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY     = os.environ.get("PICTORY_API_KEY", "")

# HeyGen — set HEYGEN_API_KEY in .env to enable avatar intros
HEYGEN_API_KEY  = os.environ.get("HEYGEN_API_KEY", "")
# HeyGen voice IDs: https://docs.heygen.com/reference/list-voices
# Default: "en-US-GuyNeural" (male) / "en-US-JennyNeural" (female)
_HEYGEN_VOICES = {
    1: "en-US-GuyNeural",    # Smart Money Daily — professional male
    2: "en-US-AriaNeural",   # AI Advantage Daily — modern female
}
HEYGEN_VOICE_ID = _HEYGEN_VOICES.get(CHANNEL, "en-US-GuyNeural")

# Background color behind the avatar (dark matches both channel styles)
_HEYGEN_BG = {
    1: "#0c1c48",   # Smart Money Daily navy
    2: "#08091e",   # AI Advantage Daily dark
}
HEYGEN_BG_COLOR = _HEYGEN_BG.get(CHANNEL, "#0c1c48")

# Presenter photo path (place on server before enabling HeyGen)
PRESENTER_PHOTO = f"presenter_ch{CHANNEL}.jpg"

YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN_FILE     = f"youtube_token_ch{CHANNEL}.json"
MAX_RETRIES            = 3

_CHANNELS = {
    1: {
        "youtube_channel_id": "UC9k4fEX_Kg5ncM1E5rEiE3A",
        "channel_name":       "Smart Money Daily",
        "niche":              "personal finance",
        "pictory_voice":      "Matthew",
        "affiliate_links": {
            "Robinhood":  "https://robinhood.com/",
            "M1 Finance": "https://m1.com/",
            "Amazon":     "https://www.amazon.com/",
        },
        "playlists": [
            "Investing & Wealth Building",
            "Budgeting & Saving Money",
            "Tax Strategies",
            "Salary & Career Money Tips",
            "Side Hustles & Extra Income",
        ],
    },
    2: {
        "youtube_channel_id": "UCwXkcGaQFoYcR64KuOYhgbA",
        "channel_name":       "AI Advantage Daily",
        "niche":              "AI tools and technology",
        "pictory_voice":      "Joanna",
        "affiliate_links": {
            "NordVPN":    "https://nordvpn.com/",
            "Skillshare": "https://www.skillshare.com/",
            "Amazon":     "https://www.amazon.com/",
        },
        "playlists": [
            "ChatGPT Tips & Tricks",
            "AI Productivity Tools",
            "AI Tool Reviews",
            "Automation & Workflows",
            "AI for Beginners",
        ],
    },
}

_ch = _CHANNELS[CHANNEL]

YOUTUBE_CHANNEL_ID = _ch["youtube_channel_id"]
CHANNEL_NAME       = _ch["channel_name"]
NICHE              = _ch["niche"]
PICTORY_VOICE      = _ch["pictory_voice"]
AFFILIATE_LINKS    = _ch["affiliate_links"]
PLAYLISTS          = _ch["playlists"]
'''

# ─────────────────────────────────────────────────────────────────────────────
# main.py — wire in avatar intro + stitch
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


def _log(msg: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\\n")


def _load_used_topics() -> list[str]:
    if os.path.exists(USED_TOPICS_FILE):
        with open(USED_TOPICS_FILE) as f:
            return json.load(f)
    return []


def _save_used_topic(topic: str) -> None:
    topics = _load_used_topics()
    topics.append(topic)
    with open(USED_TOPICS_FILE, "w") as f:
        json.dump(topics, f, indent=2)


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _notify_telegram(msg: str) -> None:
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


def _upload_short(service, video_package: dict, main_url: str, angle: str, suffix: str) -> str | None:
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


def run_pipeline() -> None:
    today        = date.today().isoformat()
    raw_path     = f"video_raw_{today}.mp4"    # Pictory output (no intro)
    video_path   = f"video_{today}.mp4"        # Final video (with intro if available)
    intro_path   = f"intro_{today}.mp4"
    thumb_path   = f"thumb_{today}.jpg"
    short_urls: list[str] = []

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

        # 4 -- Generate main video (Pictory) + avatar intro in parallel
        _log("Step 4/6 -- Generating main video (Pictory)...")
        video_generator.generate_video(
            title=package["title"],
            script=package["script"],
            scenes=package.get("scenes"),
            output_path=raw_path,
        )

        # 4b -- Generate avatar intro (HeyGen) — non-fatal
        _log("Step 4b/6 -- Generating avatar intro (HeyGen)...")
        intro = avatar_generator.generate_intro_clip(
            video_title=package["title"],
            photo_path=config.PRESENTER_PHOTO,
            output_path=intro_path,
        )

        # 4c -- Stitch intro onto main video (if intro succeeded)
        if intro:
            _log("Step 4c/6 -- Stitching intro onto main video...")
            try:
                video_stitcher.splice_intro(intro_path, raw_path, video_path)
                _log("  Intro stitched successfully")
            except Exception as stitch_exc:
                _log(f"  Stitch failed (non-fatal), using raw video: {stitch_exc}")
                os.rename(raw_path, video_path)
        else:
            _log("  No intro — using raw Pictory video")
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

        _save_used_topic(package["topic"])

        # 6 -- 2 Shorts (different angles)
        _log("Step 6/6 -- Generating and uploading Shorts (2 angles)...")
        for angle, suffix in [("stat", "a"), ("mistake", "b")]:
            short_url = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                short_urls.append(short_url)

        _log(f"SUCCESS -- {url}")

        shorts_text = ""
        for i, su in enumerate(short_urls, 1):
            shorts_text += f"\\n&#x1F3A5; Short {i}: <a href=\\"{su}\\">Watch</a>"
        avatar_line = "\\n&#x1F916; Avatar intro: ON" if intro else "\\n&#x1F916; Avatar intro: OFF (no key/photo)"
        _notify_telegram(
            f\'&#x2705; <b>{config.CHANNEL_NAME}</b>\\n\'
            f\'&#x1F4F9; <a href="{url}">{package["title"]}</a>\'
            + avatar_line + shorts_text
        )

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify_telegram(
            f\'&#x274C; <b>{config.CHANNEL_NAME}</b> pipeline failed\\n\'
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

# ── Upload ────────────────────────────────────────────────────────────────────
files = {
    "avatar_generator.py": AVATAR_GENERATOR,
    "video_stitcher.py":   VIDEO_STITCHER,
    "config.py":           CONFIG_PY,
    "main.py":             MAIN_PY,
}

for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

# Syntax check all new/modified files
checks = [
    "avatar_generator.py",
    "video_stitcher.py",
    "config.py",
    "main.py",
]
print("\nSyntax checks:")
for fname in checks:
    stdin, stdout, stderr = client.exec_command(
        f"cd {BASE} && source venv/bin/activate && python -m py_compile {fname} && echo '{fname} OK'"
    )
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err or f"{fname}: no output")

client.close()
print("\nAll done.")
