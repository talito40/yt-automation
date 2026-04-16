"""
stock_video_fallback.py
Generates a professional explainer video using Pexels stock footage + gTTS narration.
Used when HeyGen fails — produces moving video instead of a static slideshow.

Flow:
  1. Extract keywords from title/topic
  2. Search Pexels for 3 relevant video clips
  3. Generate gTTS narration audio
  4. Download + trim clips to fill audio duration
  5. ffmpeg concat + overlay audio → final MP4
"""

import os
import re
import subprocess
import tempfile
import time
import requests

import config

PEXELS_API_KEY  = os.environ.get("PEXELS_API_KEY", "")
PEXELS_BASE_URL = "https://api.pexels.com/videos/search"
TARGET_W, TARGET_H = 1280, 720


# ── Keyword extraction ─────────────────────────────────────────────────────────

_STOP_WORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "is","it","its","this","that","how","what","why","when","who","you","your",
    "my","our","we","i","ways","tips","steps","make","get","use","can","will",
    "best","top","free","using","from","into","about","more","most","do","be",
    "have","has","had","are","was","were","without","even","than","less","just",
    "month","year","week","day","people","percent","time","every","also","only",
}

# Numbers like "1000", "500", "$3000" are useless as Pexels search terms
_NUM_RE = re.compile(r"^\d+$")

# Channel-specific anchor keywords always added to searches for better results
_CHANNEL_ANCHORS = {
    1: "personal finance money",   # Smart Money Daily
    2: "artificial intelligence technology",  # AI Advantage Daily
}

def _keywords_from_title(title: str, n: int = 3) -> list[str]:
    """Extract n meaningful visual keywords from the title, skipping numbers."""
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    filtered = [
        w for w in words
        if w not in _STOP_WORDS
        and len(w) > 3
        and not _NUM_RE.match(w)
    ]
    seen = set()
    unique = [w for w in filtered if not (w in seen or seen.add(w))]
    return unique[:n]


# ── Pexels search + download ───────────────────────────────────────────────────

def _search_pexels(query: str, per_page: int = 5) -> list[dict]:
    """Return a list of Pexels video result dicts."""
    if not PEXELS_API_KEY:
        print("[stock_fallback] No PEXELS_API_KEY set — skipping")
        return []
    try:
        r = requests.get(
            PEXELS_BASE_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("videos", [])
    except Exception as e:
        print(f"[stock_fallback] Pexels search error: {e}")
        return []


def _best_file(video: dict, target_w: int = TARGET_W) -> str | None:
    """Pick the video file URL closest to target width (≤ target_w preferred)."""
    files = video.get("video_files", [])
    # Filter to mp4, landscape
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("width", 0) >= 640]
    if not mp4:
        return None
    # Prefer highest resolution ≤ target_w; fall back to lowest above
    below = [f for f in mp4 if f.get("width", 9999) <= target_w]
    if below:
        return max(below, key=lambda f: f.get("width", 0))["link"]
    return min(mp4, key=lambda f: f.get("width", 9999))["link"]


def _download_clip(url: str, output_path: str) -> bool:
    """Download a video clip from Pexels."""
    try:
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 10_000
    except Exception as e:
        print(f"[stock_fallback] Download error: {e}")
        return False


def _fetch_clips(keywords: list[str], tmp_dir: str, n_clips: int = 3) -> list[str]:
    """
    Search Pexels using each keyword, download one clip per keyword.
    Returns list of local clip paths (up to n_clips).
    """
    clip_paths = []
    used_ids   = set()

    for kw in keywords:
        if len(clip_paths) >= n_clips:
            break
        results = _search_pexels(kw, per_page=5)
        for video in results:
            vid_id = video.get("id")
            if vid_id in used_ids:
                continue
            url = _best_file(video)
            if not url:
                continue
            out = os.path.join(tmp_dir, f"clip_{len(clip_paths):02d}.mp4")
            print(f"[stock_fallback] Downloading clip for '{kw}'...")
            if _download_clip(url, out):
                clip_paths.append(out)
                used_ids.add(vid_id)
                break

    # Fallback: search with full title words combined if still short
    if len(clip_paths) < n_clips and keywords:
        combo = " ".join(keywords[:2])
        results = _search_pexels(combo, per_page=10)
        for video in results:
            if len(clip_paths) >= n_clips:
                break
            vid_id = video.get("id")
            if vid_id in used_ids:
                continue
            url = _best_file(video)
            if not url:
                continue
            out = os.path.join(tmp_dir, f"clip_{len(clip_paths):02d}.mp4")
            if _download_clip(url, out):
                clip_paths.append(out)
                used_ids.add(vid_id)

    return clip_paths


# ── Audio ──────────────────────────────────────────────────────────────────────

def _ensure_gtts():
    try:
        import gtts  # noqa
    except ImportError:
        subprocess.run(["pip", "install", "gtts"], check=True, capture_output=True)


def _generate_audio(script: str, output_path: str) -> bool:
    _ensure_gtts()
    try:
        from gtts import gTTS
        gTTS(text=script, lang="en", slow=False).save(output_path)
        return True
    except Exception as e:
        print(f"[stock_fallback] gTTS error: {e}")
        return False


def _get_audio_duration(audio_path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 60.0


def _get_video_duration(video_path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 10.0


# ── ffmpeg assembly ────────────────────────────────────────────────────────────

def _trim_and_normalise_clip(clip_path: str, duration: float, out_path: str) -> bool:
    """Trim clip to `duration` seconds and scale to 1280x720."""
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", clip_path,
            "-t", str(duration),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
                   f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast",
            "-an",                  # strip original audio
            "-pix_fmt", "yuv420p",
            out_path,
        ], capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception as e:
        print(f"[stock_fallback] Trim error: {e}")
        return False


def _concat_clips(clip_paths: list[str], tmp_dir: str) -> str | None:
    """Concatenate normalised clips into one silent video."""
    list_file = os.path.join(tmp_dir, "concat.txt")
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    out = os.path.join(tmp_dir, "concat.mp4")
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy",
            out,
        ], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(out):
            return out
        print(f"[stock_fallback] Concat error: {result.stderr[-400:]}")
        return None
    except Exception as e:
        print(f"[stock_fallback] Concat exception: {e}")
        return None


def _overlay_audio(video_path: str, audio_path: str, output_path: str) -> bool:
    """Overlay narration audio onto silent video, loop video if shorter than audio."""
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", video_path,   # loop video if needed
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac",
            "-shortest",
            "-pix_fmt", "yuv420p",
            output_path,
        ], capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return True
        print(f"[stock_fallback] Overlay error: {result.stderr[-400:]}")
        return False
    except Exception as e:
        print(f"[stock_fallback] Overlay exception: {e}")
        return False


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_stock_video(
    title: str,
    script: str,
    scenes: list = None,
    output_path: str = "stock_fallback.mp4",
) -> str:
    """
    Generate a stock-footage explainer video.
    Returns output_path on success, '' on failure.
    """
    if not PEXELS_API_KEY:
        print("[stock_fallback] PEXELS_API_KEY not set — cannot generate stock video")
        return ""

    print(f"[stock_fallback] Building stock video for: {title}")
    keywords = _keywords_from_title(title)
    # Supplement sparse keywords with channel-specific anchor terms
    anchor = _CHANNEL_ANCHORS.get(config.CHANNEL, "business success")
    if len(keywords) < 2:
        keywords = anchor.split()[:3]
    else:
        keywords.append(anchor)   # always append anchor as final search query
    print(f"[stock_fallback] Keywords: {keywords}")

    tmp_dir = tempfile.mkdtemp()
    try:
        # 1. Narration audio
        print("[stock_fallback] Generating narration audio...")
        audio_path = os.path.join(tmp_dir, "narration.mp3")
        if not _generate_audio(script, audio_path):
            return ""
        audio_dur = _get_audio_duration(audio_path)
        print(f"[stock_fallback] Audio duration: {audio_dur:.1f}s")

        # 2. Fetch stock clips
        clip_paths_raw = _fetch_clips(keywords, tmp_dir, n_clips=3)
        if not clip_paths_raw:
            print("[stock_fallback] No Pexels clips found")
            return ""
        print(f"[stock_fallback] Got {len(clip_paths_raw)} clips")

        # 3. Trim + normalise each clip
        clip_dur    = max(5.0, audio_dur / len(clip_paths_raw))
        normed      = []
        for i, raw in enumerate(clip_paths_raw):
            raw_dur  = _get_video_duration(raw)
            use_dur  = min(clip_dur, raw_dur)         # don't exceed actual length
            out_clip = os.path.join(tmp_dir, f"normed_{i:02d}.mp4")
            ok = _trim_and_normalise_clip(raw, use_dur, out_clip)
            if ok:
                normed.append(out_clip)
                print(f"[stock_fallback] Clip {i+1}/{len(clip_paths_raw)} normalised ({use_dur:.1f}s)")

        if not normed:
            print("[stock_fallback] No clips successfully normalised")
            return ""

        # 4. Concat clips
        print("[stock_fallback] Concatenating clips...")
        concat_path = _concat_clips(normed, tmp_dir)
        if not concat_path:
            return ""

        # 5. Overlay narration
        print("[stock_fallback] Overlaying narration audio...")
        ok = _overlay_audio(concat_path, audio_path, output_path)
        if ok and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) // 1_048_576
            print(f"[stock_fallback] Stock video ready: {output_path} ({size_mb} MB)")
            return output_path

        return ""

    finally:
        # Clean up temp dir
        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
