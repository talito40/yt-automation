"""
avatar_generator.py
Generates the full presenter video using HeyGen stock avatars.
HeyGen is the PRIMARY video source (not Pictory).
Falls back gracefully if HeyGen fails.
"""

import os
import re
import time
import requests
import subprocess
import tempfile

import config

HEYGEN_API_KEY  = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_BASE_URL = "https://api.heygen.com"

MAX_CHARS_PER_CHUNK = 3000   # safe limit per HeyGen video (API limit ~3500)
POLL_INTERVAL       = 15     # seconds between status checks
MAX_POLL_ATTEMPTS   = 160    # 160 * 15s = 40 minutes max wait per chunk

# Set by _generate_single() when HeyGen rejects due to insufficient credits.
# main.py reads this to send a targeted Telegram alert even when fallback succeeds.
LAST_FAILURE_REASON = ""


def _build_full_script(script: str, scenes: list) -> str:
    """Return the best available script text."""
    if script and len(script.strip()) > 100:
        return script.strip()
    if scenes:
        parts = []
        for s in scenes:
            narration = s.get("narration") or s.get("text") or ""
            if narration:
                parts.append(narration.strip())
        combined = " ".join(parts)
        if len(combined) > 100:
            return combined
    return script.strip() if script else ""


def _split_script(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list:
    """Split text into chunks at sentence boundaries, each <= max_chars."""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if not sentence.strip():
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            # If a single sentence is too long, hard-split it
            if len(sentence) > max_chars:
                words = sentence.split()
                part = ""
                for word in words:
                    if len(part) + len(word) + 1 <= max_chars:
                        part = (part + " " + word).strip() if part else word
                    else:
                        if part:
                            chunks.append(part)
                        part = word
                if part:
                    current = part
                else:
                    current = ""
            else:
                current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:max_chars]]


def _generate_single(script_text: str, output_path: str) -> bool:
    """
    Submit one HeyGen video job and download result to output_path.
    Returns True on success, False on failure.
    """
    avatar_id = config.HEYGEN_AVATAR_ID
    voice_id  = config.HEYGEN_VOICE_ID

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
                    "input_text": script_text,
                    "voice_id": voice_id,
                },
                "background": {
                    "type": "color",
                    "value": "#f0f4f8",
                },
            }
        ],
        "dimension": {"width": 1920, "height": 1080},
        "aspect_ratio": "16:9",
    }

    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    # Submit job
    try:
        resp = requests.post(
            f"{HEYGEN_BASE_URL}/v2/video/generate",
            json=payload,
            headers=headers,
            timeout=30,
        )
    except Exception as e:
        print(f"[avatar_generator] HeyGen submit error: {e}")
        return False

    if resp.status_code != 200:
        print(f"[avatar_generator] HeyGen submit failed: {resp.status_code} {resp.text[:300]}")
        return False

    data = resp.json()
    video_id = data.get("data", {}).get("video_id") or data.get("video_id")
    if not video_id:
        print(f"[avatar_generator] No video_id in response: {data}")
        return False

    print(f"[avatar_generator] Submitted video_id={video_id}, polling...")

    # Poll for completion
    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL)
        try:
            status_resp = requests.get(
                f"{HEYGEN_BASE_URL}/v1/video_status.get?video_id={video_id}",
                headers=headers,
                timeout=15,
            )
        except Exception as e:
            print(f"[avatar_generator] Poll error (attempt {attempt+1}): {e}")
            continue

        if status_resp.status_code != 200:
            print(f"[avatar_generator] Poll failed: {status_resp.status_code}")
            continue

        sdata  = status_resp.json().get("data", {})
        status = sdata.get("status", "")
        print(f"[avatar_generator] Status: {status} (attempt {attempt+1}/{MAX_POLL_ATTEMPTS})")

        if status == "completed":
            video_url = sdata.get("video_url") or sdata.get("download_url")
            if not video_url:
                print("[avatar_generator] No video_url in completed response")
                return False
            # Download
            try:
                dl = requests.get(video_url, timeout=120, stream=True)
                with open(output_path, "wb") as f:
                    for chunk in dl.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                print(f"[avatar_generator] Downloaded -> {output_path}")
                return True
            except Exception as e:
                print(f"[avatar_generator] Download error: {e}")
                return False

        elif status in ("failed", "error"):
            err = sdata.get("error") or sdata.get("message", "unknown")
            print(f"[avatar_generator] HeyGen generation failed: {err}")
            if "MOVIO_PAYMENT_INSUFFICIENT_CREDIT" in str(err):
                global LAST_FAILURE_REASON
                LAST_FAILURE_REASON = "INSUFFICIENT_CREDIT"
            return False

    print(f"[avatar_generator] Timed out waiting for video_id={video_id}")
    return False


def _stitch_videos(chunk_paths: list, output_path: str) -> bool:
    """Concatenate multiple mp4 files using ffmpeg concat demuxer."""
    if len(chunk_paths) == 1:
        import shutil
        shutil.copy2(chunk_paths[0], output_path)
        return True

    # Write concat list file
    list_file = output_path + "_concat_list.txt"
    try:
        with open(list_file, "w") as f:
            for p in chunk_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[avatar_generator] ffmpeg stitch error: {result.stderr[-500:]}")
            return False
        print(f"[avatar_generator] Stitched {len(chunk_paths)} chunks -> {output_path}")
        return True
    except Exception as e:
        print(f"[avatar_generator] Stitch exception: {e}")
        return False
    finally:
        try:
            os.remove(list_file)
        except OSError:
            pass


def generate_intro_clip(
    video_title: str,
    script: str = "",
    scenes: list = None,
    photo_path: str = None,
    output_path: str = "intro.mp4",
) -> str:
    """
    Generate the full presenter video via HeyGen.
    Returns output_path on success, empty string on failure.

    photo_path is accepted for API compatibility but ignored (using stock avatars).
    """
    if not HEYGEN_API_KEY:
        print("[avatar_generator] No HEYGEN_API_KEY â€” skipping")
        return ""

    if scenes is None:
        scenes = []

    full_script = _build_full_script(script, scenes)
    if not full_script:
        full_script = f"Welcome! Today we're talking about {video_title}."

    print(f"[avatar_generator] Script length: {len(full_script)} chars")
    print(f"[avatar_generator] Avatar: {config.HEYGEN_AVATAR_ID}, Voice: {config.HEYGEN_VOICE_ID}")

    chunks = _split_script(full_script)
    print(f"[avatar_generator] Split into {len(chunks)} chunk(s)")

    chunk_paths = []
    tmp_dir = tempfile.mkdtemp()

    try:
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmp_dir, f"chunk_{i:02d}.mp4")
            print(f"[avatar_generator] Generating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
            ok = _generate_single(chunk, chunk_path)
            if not ok:
                print(f"[avatar_generator] Chunk {i+1} failed â€” aborting")
                return ""
            chunk_paths.append(chunk_path)

        ok = _stitch_videos(chunk_paths, output_path)
        if ok:
            return output_path
        else:
            return ""

    finally:
        # Clean up temp chunks
        for p in chunk_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
