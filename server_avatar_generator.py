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
