"""
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
