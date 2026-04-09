"""
deploy_marktilbury_style.py

Upgrades the pipeline to match Mark Tilbury's YouTube style:
1. content_generator.py  — numbered-list titles, hook-driven scripts, ~18 min structure
2. thumb_generator.py    — bold face+number thumbnails, yellow/white on dark background
3. avatar_generator.py   — energetic hook-style intro script
"""

import paramiko, py_compile, tempfile, os

HOST, USER, PASSWD = "165.22.33.167", "root", "LukaKi2001q"
REMOTE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
# 1. content_generator.py  — Mark Tilbury title/script style
# ─────────────────────────────────────────────────────────────────────────────
CONTENT_GENERATOR_PY = r'''"""
content_generator.py
SEO research + script generation.
Style: Mark Tilbury — numbered lists, shocking hooks, specific dollar amounts.
"""

import os
import json
import anthropic
from pytrends.request import TrendReq
import config

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── SEO research ──────────────────────────────────────────────────────────────

def get_trending_keywords(niche: str) -> list[str]:
    """Returns top trending keywords for the niche via Google Trends."""
    try:
        pt = TrendReq(hl="en-US", tz=360)
        query = niche.split()[0]
        pt.build_payload([query], cat=0, timeframe="now 7-d", geo="US")
        related = pt.related_queries()
        keywords = []
        for val in related.values():
            if val and val.get("top") is not None:
                keywords += val["top"]["query"].tolist()[:5]
        return keywords[:10] if keywords else [niche]
    except Exception as e:
        print(f"[content] Trends error: {e}")
        return [niche]


def research_seo_topic(niche: str, trending_keywords: list[str]) -> dict:
    """Uses Claude to pick the best SEO topic from trending keywords."""
    kw_str = ", ".join(trending_keywords[:10])
    prompt = f"""You are a YouTube SEO expert specialising in {niche}.

Trending keywords right now: {kw_str}

Pick the SINGLE best video topic that:
- Has high search volume + low competition
- Fits the {niche} niche
- Works as a "how to make / save / invest money" style video
- Can be structured as a numbered list (5 tips, 7 ways, 3 mistakes, etc.)

Return JSON only:
{{
  "topic": "...",
  "search_volume": "high/medium",
  "competition": "low/medium",
  "reasoning": "one sentence"
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    try:
        return json.loads(text)
    except Exception:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {"topic": trending_keywords[0]}


def generate_video_package(topic: str, niche: str) -> dict:
    """
    Generates a full Mark Tilbury-style video package:
    - Catchy numbered-list title
    - 18-minute script broken into 8-10 scenes with hook
    - Chapters, playlist, hashtags
    """
    prompt = f"""You are a YouTube scriptwriter copying Mark Tilbury's exact style.

Topic: {topic}
Niche: {niche}

Mark Tilbury's formula:
- Title: Number + Specific Outcome (always include a $ amount or %) — e.g. "7 Ways to Make $1,000/Month", "5 Money Mistakes Costing You $10,000/Year", "The $500/Week Side Hustle Nobody Talks About"
- Hook (scene 1): Open with a SHOCKING STAT or BOLD CLAIM in first 10 seconds. No intro, no greeting. Start mid-sentence with urgency.
  Example: "Most people will never build wealth, and it's not because they don't work hard enough..."
- Structure: numbered sections (e.g. "Number 1:", "Number 2:", etc.)
- Each point: specific, actionable, include real dollar amounts, percentages, timeframes
- Tone: direct, conversational, no fluff, like talking to a friend who is a millionaire
- Length: 8 scenes that together form ~18 minutes of content (~2 min per scene)
- End with a strong CTA: "If this helped, subscribe — I post strategies like this every week"

Return VALID JSON only, no markdown, no extra text:
{{
  "title": "...",
  "description": "...(150 words, includes 5 hashtags like #personalfinance #moneytips at end)",
  "scenes": [
    {{
      "narration": "...(250-300 words, punchy, direct)",
      "visuals": "...(b-roll suggestion)"
    }}
  ],
  "chapters": [
    {{"time": "0:00", "title": "..."}},
    {{"time": "2:00", "title": "..."}}
  ],
  "playlist": "...(pick most relevant playlist from: {config.PLAYLISTS})",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"]
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception as e:
        print(f"[content] JSON parse error: {e}\nRaw: {text[:300]}")
        return {
            "title": f"7 Ways to Build Wealth with {topic}",
            "description": f"In this video we break down {topic}. #personalfinance #moneytips #investing #wealth #finance",
            "scenes": [{"narration": f"Today we are covering {topic}.", "visuals": "charts and graphs"}],
            "chapters": [{"time": "0:00", "title": "Introduction"}],
            "playlist": config.PLAYLISTS[0],
            "tags": [niche, topic, "money", "finance", "investing"],
        }


def generate_shorts_script(topic: str, niche: str, angle: str = "stat") -> dict:
    """
    Generates a 45-60 second Shorts script in Mark Tilbury hook style.
    angle: 'stat' | 'mistake' | 'secret'
    """
    angle_prompts = {
        "stat":    f"Start with a shocking financial stat about {topic}. Make it feel unbelievable but true.",
        "mistake": f"Open with 'The #1 mistake people make with {topic} is...' then flip it with the solution.",
        "secret":  f"Open with 'Nobody talks about this {topic} strategy...' — share one specific, actionable tip.",
    }
    angle_text = angle_prompts.get(angle, angle_prompts["stat"])

    prompt = f"""Write a 45-60 second YouTube Shorts script in Mark Tilbury's style.
Niche: {niche}
Topic: {topic}
Angle: {angle_text}

Rules:
- No greeting, start IMMEDIATELY with the hook
- Every sentence must add value — no filler
- End with "Follow for more" or "Save this for later"
- Include specific numbers/dollar amounts

Return JSON only:
{{
  "title": "...(max 60 chars, curiosity-gap style)",
  "script": "...(full word-for-word script, 120-150 words)",
  "hook": "...(first sentence only)"
}}"""

    msg = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return {
            "title": f"{topic} tip you need to know",
            "script": f"Here is what you need to know about {topic}. Follow for more.",
            "hook": f"Here is what you need to know about {topic}.",
        }
'''

# ─────────────────────────────────────────────────────────────────────────────
# 2. thumb_generator.py  — Mark Tilbury thumbnail style
# ─────────────────────────────────────────────────────────────────────────────
THUMB_GENERATOR_PY = r'''"""
thumb_generator.py
Generates YouTube thumbnails in Mark Tilbury's style:
- Bold yellow/white text, big dollar number or stat
- Avatar face on one side (expressive)
- Dark gradient background
- High contrast, clean 2-3 element composition
Falls back to Pillow if Leonardo fails.
"""

import os
import time
import re
import textwrap
import requests
import config

LEONARDO_API_KEY = config.LEONARDO_API_KEY
LEONARDO_BASE    = "https://cloud.leonardo.ai/api/rest/v1"
PHOENIX_MODEL_ID = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"
CINEMATIC_STYLE  = "a5632c7c-ddbb-4e2f-ba34-8456ab3ac436"


def _extract_number(title: str) -> str:
    """Pull out the most impactful number/stat from the title for the thumbnail."""
    # Match $X,XXX or X% or plain integers >= 2 digits
    patterns = [r'\$[\d,]+[KkMm]?', r'\d+%', r'\b\d{2,}\b']
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            return m.group()
    # Return first word if number
    first = title.split()[0]
    return first if first[0].isdigit() else ""


def _build_thumbnail_prompt(title: str, niche: str) -> str:
    """
    Builds a Leonardo prompt that mimics Mark Tilbury's thumbnail style:
    dark background, bold text, expressive presenter, money imagery.
    """
    number = _extract_number(title)
    # Shorten title to 4-5 words for thumbnail text
    short_words = title.split()[:5]
    short_text  = " ".join(short_words)

    number_line = f'giant bold yellow number "{number}" ' if number else ""

    prompt = (
        f"YouTube thumbnail, Mark Tilbury style, "
        f"dark navy gradient background, "
        f"left side: professional male presenter in light blue blazer, "
        f"shocked/excited expression, pointing right, "
        f"right side: {number_line}"
        f'bold white text "{short_text}", '
        f"yellow accent highlights, money imagery, "
        f"high contrast, ultra sharp, 1280x720, "
        f"cinematic lighting, photorealistic, "
        f"text is crisp and readable, no blur, "
        f"style of top finance YouTube thumbnails"
    )
    return prompt


def generate_thumbnail(title: str, output_path: str = "thumbnail.jpg") -> str:
    """Main entry point. Tries Leonardo first, falls back to Pillow."""
    if LEONARDO_API_KEY:
        try:
            return _generate_with_leonardo(title, output_path)
        except Exception as e:
            print(f"[thumb] Leonardo failed: {e} — falling back to Pillow")
    return _generate_with_pillow(title, output_path)


def _generate_with_leonardo(title: str, output_path: str) -> str:
    headers = {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json",
    }

    niche  = config.NICHE
    prompt = _build_thumbnail_prompt(title, niche)
    print(f"[thumb] Leonardo prompt: {prompt[:120]}...")

    # 1. Submit generation
    payload = {
        "prompt": prompt,
        "negative_prompt": "text errors, blurry text, watermark, ugly, distorted face, extra limbs",
        "modelId": PHOENIX_MODEL_ID,
        "width": 1280,
        "height": 720,
        "num_images": 1,
        "guidance_scale": 7,
        "styleUUID": CINEMATIC_STYLE,
        "public": False,
    }
    r = requests.post(f"{LEONARDO_BASE}/generations", headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    gen_id = r.json()["sdGenerationJob"]["generationId"]
    print(f"[thumb] Leonardo generation started: {gen_id}")

    # 2. Poll until ready
    for attempt in range(30):
        time.sleep(8)
        r = requests.get(f"{LEONARDO_BASE}/generations/{gen_id}", headers=headers, timeout=20)
        r.raise_for_status()
        data   = r.json().get("generations_by_pk", {})
        status = data.get("status", "").upper()
        print(f"[thumb] Status: {status}")
        if status == "COMPLETE":
            images = data.get("generated_images", [])
            if not images:
                raise RuntimeError("No images in Leonardo response")
            url = images[0]["url"]
            img_r = requests.get(url, timeout=30)
            img_r.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(img_r.content)
            print(f"[thumb] Saved thumbnail -> {output_path}")
            return output_path
        if status in ("FAILED", "ERROR"):
            raise RuntimeError(f"Leonardo generation failed: {data}")

    raise TimeoutError("Leonardo thumbnail timed out")


def _generate_with_pillow(title: str, output_path: str) -> str:
    """Fallback: generates a stylised Mark Tilbury-style thumbnail using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import math

        W, H = 1280, 720
        img  = Image.new("RGB", (W, H), color=(10, 20, 60))   # dark navy
        draw = ImageDraw.Draw(img)

        # Gradient overlay
        for y in range(H):
            alpha = int(40 * (1 - y / H))
            draw.line([(0, y), (W, y)], fill=(alpha, alpha, alpha + 20))

        # Yellow accent bar on left
        draw.rectangle([0, 0, 12, H], fill=(255, 200, 0))

        # Extract number
        number = _extract_number(title)

        # Title text — wrapped
        try:
            font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            font_num   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
        except Exception:
            font_big = font_num = font_small = ImageFont.load_default()

        # Big number in yellow
        if number:
            draw.text((680, 120), number, font=font_num, fill=(255, 220, 0))

        # Title words
        words = title.split()
        line1 = " ".join(words[:4])
        line2 = " ".join(words[4:8]) if len(words) > 4 else ""
        draw.text((80, 300), line1, font=font_big, fill=(255, 255, 255))
        if line2:
            draw.text((80, 390), line2, font=font_big, fill=(255, 255, 200))

        # Channel branding
        ch_name = config.CHANNEL_NAME
        draw.text((80, H - 70), ch_name, font=font_small, fill=(255, 200, 0))

        # Bottom accent bar
        draw.rectangle([0, H - 8, W, H], fill=(255, 200, 0))

        img.save(output_path, "JPEG", quality=95)
        print(f"[thumb] Pillow fallback thumbnail saved -> {output_path}")
        return output_path

    except Exception as e:
        print(f"[thumb] Pillow also failed: {e}")
        return output_path
'''

# ─────────────────────────────────────────────────────────────────────────────
# 3. avatar_generator.py  — energetic Mark Tilbury-style intro
# ─────────────────────────────────────────────────────────────────────────────
AVATAR_PY = r'''"""
avatar_generator.py
Generates a talking-head intro using HeyGen stock avatars.
Intro style: Mark Tilbury — hook-first, no fluff, direct to value.

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
    """
    Mark Tilbury-style intro: no greeting, straight to the hook.
    ~20 seconds, creates urgency, promises specific value.
    """
    title = video_title.rstrip(".!?")

    # Extract number from title if present
    import re
    num_match = re.search(r'(\$[\d,]+[KkMm]?|\d+%|\d+ \w+)', title)
    number_hook = f" — we are talking {num_match.group()} here" if num_match else ""

    return (
        f"Most people get {title} completely wrong{number_hook}. "
        f"In the next few minutes I am going to show you exactly what the top one percent do differently, "
        f"and how you can copy it starting today. "
        f"Let's get straight into it."
    )


def generate_intro_clip(
    video_title: str,
    photo_path: str = None,
    output_path: str = "intro.mp4",
) -> str | None:
    """
    Generates a ~20-second talking-head intro using a HeyGen stock avatar.
    Returns the absolute path to the downloaded MP4, or None on failure.
    """
    if not config.HEYGEN_API_KEY:
        print("[avatar] HEYGEN_API_KEY not set — skipping avatar intro")
        return None

    avatar_id = config.HEYGEN_AVATAR_ID
    print(f"[avatar] Using stock avatar: {avatar_id}")

    try:
        intro_text = _build_intro_script(video_title)
        print(f"[avatar] Intro script: {intro_text[:100]}...")

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
    "content_generator.py": CONTENT_GENERATOR_PY,
    "thumb_generator.py":   THUMB_GENERATOR_PY,
    "avatar_generator.py":  AVATAR_PY,
}


def syntax_ok(code: str, name: str) -> bool:
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

    client.close()

    print("""
Done. Mark Tilbury style applied:

  content_generator.py
    Titles  : Number + Outcome format ("7 Ways to Make $X", "5 Mistakes Costing You $X")
    Scripts : Hook-first, numbered sections, specific $ amounts, ~18 min length
    Shorts  : stat / mistake / secret angles

  thumb_generator.py
    Leonardo: dark navy bg + face (left) + bold yellow number + white title text
    Pillow  : same layout as fallback

  avatar_generator.py
    Intro   : "Most people get X completely wrong..." hook, no greeting, 20 seconds
""")


if __name__ == "__main__":
    main()
