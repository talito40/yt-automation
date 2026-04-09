"""Deploy Leonardo.ai thumbnail integration to the droplet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
# thumb_generator.py
# Uses Leonardo.ai to generate a professional 1280x720 thumbnail.
# Falls back to the Pillow generator if Leonardo fails.
# ─────────────────────────────────────────────────────────────────────────────
THUMB_GENERATOR = '''\
"""
thumb_generator.py
Generates a 1280x720 YouTube thumbnail using Leonardo.ai.
Falls back to Pillow if the API fails or key is missing.
"""

import os
import time
import textwrap
import requests
import config

LEONARDO_BASE  = "https://cloud.leonardo.ai/api/rest/v1"
# Phoenix 1.0 — flagship model, excellent for cinematic/professional imagery
PHOENIX_MODEL  = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"
# Cinematic style UUID for Phoenix
CINEMATIC_UUID = "a5632c7c-ddbb-4e2f-ba34-8456ab3ac436"
HDR_UUID       = "97c20e5c-1af6-4d42-b227-54d03d8f0727"


def _leonardo_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.LEONARDO_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Per-channel prompt styles ──────────────────────────────────────────────────

_CHANNEL_PROMPTS = {
    1: {  # Smart Money Daily — finance
        "style": "professional corporate financial photography, money and wealth aesthetic",
        "mood":  "confident, aspirational, clean navy and gold color palette",
        "neg":   "cartoon, anime, ugly, blurry, watermark, text, low quality, amateur",
    },
    2: {  # AI Advantage Daily — tech/AI
        "style": "futuristic technology photography, neon cyan and dark blue aesthetic",
        "mood":  "cutting edge, innovative, dark background with glowing tech elements",
        "neg":   "cartoon, anime, ugly, blurry, watermark, text, low quality, amateur",
    },
}


def _build_prompt(title: str) -> tuple[str, str]:
    """Returns (prompt, negative_prompt) tailored to channel and video title."""
    ch     = _CHANNEL_PROMPTS.get(config.CHANNEL, _CHANNEL_PROMPTS[1])
    # Strip punctuation for cleaner prompt embedding
    clean  = title.rstrip(".!?,;:")

    prompt = (
        f"YouTube thumbnail, {ch['style']}, "
        f"cinematic scene visualising the concept of: {clean}, "
        f"{ch['mood']}, "
        f"dramatic lighting, ultra sharp, 4K, professional photography, "
        f"thumbnail-ready composition, bold visual impact, no text"
    )
    return prompt, ch["neg"]


def _generate_with_leonardo(title: str, output_path: str) -> str:
    """Calls Leonardo API, polls for result, downloads image. Returns abs path."""
    prompt, negative = _build_prompt(title)

    payload = {
        "prompt":          prompt,
        "negativePrompt":  negative,
        "modelId":         PHOENIX_MODEL,
        "styleUUID":       CINEMATIC_UUID,
        "width":           1280,
        "height":          720,
        "num_images":      1,
        "alchemy":         True,
        "guidance_scale":  7,
        "num_inference_steps": 20,
    }

    headers = _leonardo_headers()

    # Submit generation
    resp = requests.post(f"{LEONARDO_BASE}/generations",
                         headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    gen_id = resp.json()["sdGenerationJob"]["generationId"]
    print(f"[thumb] Leonardo generation started, id={gen_id}")

    # Poll until complete (max 3 min)
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(4)
        r = requests.get(f"{LEONARDO_BASE}/generations/{gen_id}",
                         headers=headers, timeout=20)
        r.raise_for_status()
        data   = r.json().get("generations_by_pk", {})
        status = data.get("status", "")
        print(f"[thumb] Leonardo status: {status}")

        if status == "COMPLETE":
            images = data.get("generated_images", [])
            if not images:
                raise RuntimeError("Leonardo returned COMPLETE but no images")
            image_url = images[0]["url"]
            break
        elif status == "FAILED":
            raise RuntimeError(f"Leonardo generation failed: {data}")
    else:
        raise TimeoutError("Leonardo generation timed out after 3 minutes")

    # Download
    img_resp = requests.get(image_url, timeout=60)
    img_resp.raise_for_status()
    abs_path = os.path.abspath(output_path)
    with open(abs_path, "wb") as f:
        f.write(img_resp.content)
    size_kb = len(img_resp.content) // 1024
    print(f"[thumb] Leonardo thumbnail saved -> {abs_path} ({size_kb} KB)")
    return abs_path


def _generate_with_pillow(title: str, output_path: str) -> str:
    """Fallback: simple branded thumbnail using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    _STYLES = {
        1: {"bg": (12, 28, 72),  "accent": (255, 196, 0),  "text": (255, 255, 255)},
        2: {"bg": (8,  10, 30),  "accent": (0, 200, 255),  "text": (255, 255, 255)},
    }
    W, H  = 1280, 720
    style = _STYLES.get(config.CHANNEL, _STYLES[1])
    bg, accent, white = style["bg"], style["accent"], style["text"]

    img  = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    for x in range(W):
        dim = int(60 * x / W)
        col = tuple(max(0, c - dim) for c in bg)
        draw.line([(x, 0), (x, H)], fill=col)
    draw.rectangle([(0, 0), (14, H)], fill=accent)
    draw.rectangle([(0, 0), (W, 8)],  fill=accent)

    try:
        font_title = ImageFont.truetype(FONT_BOLD, 86)
        font_ch    = ImageFont.truetype(FONT_REG,  38)
    except OSError:
        font_title = ImageFont.load_default()
        font_ch    = ImageFont.load_default()

    wrapped = textwrap.wrap(title, width=22)[:3]
    line_h  = 96
    y       = (H - len(wrapped) * line_h) // 2 - 20
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        x    = max(40, (W - (bbox[2] - bbox[0])) // 2)
        draw.text((x + 3, y + 3), line, font=font_title, fill=(0, 0, 0))
        draw.text((x,     y),     line, font=font_title, fill=white)
        y += line_h

    bbox = draw.textbbox((0, 0), config.CHANNEL_NAME, font=font_ch)
    draw.text((W - bbox[2] - 30, H - 60), config.CHANNEL_NAME, font=font_ch, fill=accent)

    abs_path = os.path.abspath(output_path)
    img.save(abs_path, "JPEG", quality=95)
    print(f"[thumb] Pillow fallback thumbnail saved -> {abs_path}")
    return abs_path


def generate_thumbnail(title: str, output_path: str = "thumbnail.jpg") -> str:
    """
    Generates a 1280x720 thumbnail.
    Uses Leonardo.ai if LEONARDO_API_KEY is set, otherwise falls back to Pillow.
    """
    if config.LEONARDO_API_KEY:
        try:
            return _generate_with_leonardo(title, output_path)
        except Exception as exc:
            print(f"[thumb] Leonardo failed ({exc}), falling back to Pillow")

    return _generate_with_pillow(title, output_path)
'''

# ─────────────────────────────────────────────────────────────────────────────
# config.py — add LEONARDO_API_KEY
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PY = '''\
import os

CHANNEL = int(os.environ.get("CHANNEL", "1"))

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY     = os.environ.get("PICTORY_API_KEY", "")
HEYGEN_API_KEY      = os.environ.get("HEYGEN_API_KEY", "")
LEONARDO_API_KEY    = os.environ.get("LEONARDO_API_KEY", "")

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

# ── Upload files ──────────────────────────────────────────────────────────────
files = {
    "thumb_generator.py": THUMB_GENERATOR,
    "config.py":          CONFIG_PY,
}

for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

# Add Leonardo API key to .env
stdin, stdout, stderr = client.exec_command(
    'echo "LEONARDO_API_KEY=03bc47f5-2368-4a26-be70-bca0f25c46a7" >> /opt/yt-automation/.env && echo done'
)
print("  .env updated:", stdout.read().decode().strip())

# Syntax check
checks = ["thumb_generator.py", "config.py"]
print("\nSyntax checks:")
for fname in checks:
    stdin, stdout, stderr = client.exec_command(
        f"cd {BASE} && source venv/bin/activate && python -m py_compile {fname} && echo '{fname} OK'"
    )
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err or f"{fname}: no output")

# Quick API test
print("\nTesting Leonardo API key...")
stdin, stdout, stderr = client.exec_command(
    'curl -s -o /dev/null -w "%{http_code}" '
    '-H "Authorization: Bearer 03bc47f5-2368-4a26-be70-bca0f25c46a7" '
    'https://cloud.leonardo.ai/api/rest/v1/me'
)
code = stdout.read().decode().strip()
print(f"  Leonardo /me response: HTTP {code}", "✓" if code == "200" else "✗ (check key)")

client.close()
print("\nAll done.")
