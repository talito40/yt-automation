"""
deploy_stock_avatars.py
Switches both channels from custom photo avatars to HeyGen stock avatars:
  Ch1 (Smart Money Daily)   -> Albert in Blue Suit  (Albert_public_1)
  Ch2 (AI Advantage Daily)  -> Annie Business Casual (Annie_Business_Casual_Standing_Front_public)
"""

import paramiko, py_compile, tempfile, os, textwrap

HOST, USER, PASSWD = "165.22.33.167", "root", "LukaKi2001q"
REMOTE = "/opt/yt-automation"

# ── Updated config.py ─────────────────────────────────────────────────────────
CONFIG_PY = '''\
import os

CHANNEL = int(os.environ.get("CHANNEL", "1"))

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY     = os.environ.get("PICTORY_API_KEY", "")
HEYGEN_API_KEY      = os.environ.get("HEYGEN_API_KEY", "")
LEONARDO_API_KEY    = os.environ.get("LEONARDO_API_KEY", "")

# HeyGen stock avatar IDs (no photo upload needed)
_HEYGEN_AVATARS = {
    1: "Albert_public_1",                             # Albert – light blue blazer, friendly/trustworthy
    2: "Annie_Business_Casual_Standing_Front_public", # Annie  – grey blazer, tech office background
}
HEYGEN_AVATAR_ID = _HEYGEN_AVATARS.get(CHANNEL, "Albert_public_1")

_HEYGEN_VOICES = {
    1: "en-US-GuyNeural",
    2: "en-US-AriaNeural",
}
HEYGEN_VOICE_ID = _HEYGEN_VOICES.get(CHANNEL, "en-US-GuyNeural")

_HEYGEN_BG = {
    1: "#0c1c48",
    2: "#08091e",
}
HEYGEN_BG_COLOR = _HEYGEN_BG.get(CHANNEL, "#0c1c48")

# Legacy – kept so old references don\'t break, but no longer used by avatar_generator
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

# ── Updated avatar_generator.py ───────────────────────────────────────────────
AVATAR_PY = '''\
"""
avatar_generator.py
Generates a short talking-head intro clip via HeyGen API using
pre-built stock avatars (no photo upload required).

Ch1: Albert_public_1                             (Albert – light blue blazer)
Ch2: Annie_Business_Casual_Standing_Front_public (Annie  – tech office background)
"""

import os
import time
import requests
import config

HEYGEN_BASE = "https://api.heygen.com"


def _headers() -> dict:
    return {
        "X-Api-Key": config.HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _build_intro_script(video_title: str) -> str:
    """12-15 second punchy spoken intro."""
    title = video_title.rstrip(".!?")
    return (
        f"Hey, welcome back. Today we are breaking down {title}. "
        f"Stay with me — this one is going to save you a lot of money and time. "
        f"Let\'s get into it."
    )


def generate_intro_clip(
    video_title: str,
    photo_path: str = None,   # kept for backwards-compat, no longer used
    output_path: str = "intro.mp4",
) -> str | None:
    """
    Generates a ~15-second talking-head intro using a HeyGen stock avatar.
    Returns the absolute path to the downloaded MP4, or None on failure.
    """
    if not config.HEYGEN_API_KEY:
        print("[avatar] HEYGEN_API_KEY not set — skipping avatar intro")
        return None

    avatar_id = config.HEYGEN_AVATAR_ID
    print(f"[avatar] Using stock avatar: {avatar_id}")

    try:
        intro_text = _build_intro_script(video_title)

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
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

FILES = {
    "config.py":           CONFIG_PY,
    "avatar_generator.py": AVATAR_PY,
}

def syntax_ok(code: str, name: str) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        print(f"  syntax OK  {name}")
        return True
    except py_compile.PyCompileError as e:
        print(f"  SYNTAX ERR {name}: {e}")
        return False
    finally:
        os.unlink(tmp)

def main():
    # 1. syntax check locally
    print("Syntax checks:")
    for name, code in FILES.items():
        if not syntax_ok(code, name):
            raise SystemExit("Fix syntax errors before deploying.")

    # 2. deploy via SFTP
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWD)
    sftp = client.open_sftp()

    print("\nUploading:")
    for name, code in FILES.items():
        remote_path = f"{REMOTE}/{name}"
        with sftp.open(remote_path, "w") as rf:
            rf.write(code)
        print(f"  uploaded {name}")

    sftp.close()

    # 3. remote syntax check
    print("\nRemote syntax checks:")
    for name in FILES:
        _, stdout, stderr = client.exec_command(
            f"cd {REMOTE} && python3 -c \"import py_compile; py_compile.compile('{name}', doraise=True)\" 2>&1"
        )
        out = (stdout.read() + stderr.read()).decode().strip()
        print(f"  {name}: {'OK' if not out else out}")

    client.close()
    print("\nDone. Next pipeline run will use:")
    print("  Ch1 -> Albert_public_1 (Albert, light blue blazer)")
    print("  Ch2 -> Annie_Business_Casual_Standing_Front_public (Annie, tech office)")

if __name__ == "__main__":
    main()
