"""
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
