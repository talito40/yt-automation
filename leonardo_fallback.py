"""
leonardo_fallback.py
Fallback video generator when HeyGen fails or has insufficient credits.

Pipeline:
  1. Generate 3 scene images via Leonardo.ai (based on script/title)
  2. Generate narration audio via gTTS (free Google TTS)
  3. Stitch images + audio into MP4 using ffmpeg

No extra subscriptions needed — uses existing Leonardo plan + free gTTS.
"""

import os
import re
import time
import requests
import subprocess
import tempfile

import config

LEONARDO_API_KEY = config.LEONARDO_API_KEY
LEONARDO_BASE    = "https://cloud.leonardo.ai/api/rest/v1"
PHOENIX_MODEL    = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"

# seconds each image slide is shown (total = num_slides * SLIDE_DURATION)
SLIDE_DURATION = 5   # will be overridden to match audio length


def _ensure_gtts():
    """Install gTTS if not present."""
    try:
        import gtts  # noqa
    except ImportError:
        subprocess.run(
            ["pip", "install", "gtts", "-q"],
            capture_output=True,
        )


def _generate_scene_image(prompt: str, output_path: str) -> bool:
    """Generate one image with Leonardo and save to output_path."""
    if not LEONARDO_API_KEY:
        return False

    headers = {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build a visual prompt (not the narration text — a visual description)
    visual_prompt = (
        f"Professional YouTube video frame, dark navy background, "
        f"bold white text overlay, high contrast, cinematic, {prompt}, "
        f"no people, clean minimal design, 16:9 aspect ratio"
    )

    payload = {
        "modelId":   PHOENIX_MODEL,
        "prompt":    visual_prompt,
        "width":     1280,   # 1280x720 = 16:9, confirmed working in thumb_generator
        "height":    720,
        "num_images": 1,
        "alchemy":   True,
    }

    try:
        r = requests.post(f"{LEONARDO_BASE}/generations", headers=headers,
                          json=payload, timeout=30)
        if r.status_code != 200:
            print(f"[fallback] Leonardo generate error: {r.status_code} {r.text[:200]}")
            return False

        gen_id = r.json().get("sdGenerationJob", {}).get("generationId")
        if not gen_id:
            return False

        # Poll until complete
        for _ in range(20):
            time.sleep(4)
            sr = requests.get(f"{LEONARDO_BASE}/generations/{gen_id}",
                              headers=headers, timeout=15)
            gen = sr.json().get("generations_by_pk", {})
            status = gen.get("status", "")
            if status == "COMPLETE":
                images = gen.get("generated_images", [])
                if images:
                    img_url = images[0].get("url")
                    dl = requests.get(img_url, timeout=30)
                    with open(output_path, "wb") as f:
                        f.write(dl.content)
                    return True
            elif status == "FAILED":
                print(f"[fallback] Leonardo generation failed")
                return False

        print(f"[fallback] Leonardo timed out")
        return False

    except Exception as e:
        print(f"[fallback] Leonardo exception: {e}")
        return False


def _generate_audio(script: str, output_path: str) -> bool:
    """Generate narration audio using gTTS."""
    _ensure_gtts()
    try:
        from gtts import gTTS
        tts = gTTS(text=script, lang="en", slow=False)
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"[fallback] gTTS error: {e}")
        return False


def _get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 60.0  # fallback estimate


def _build_visual_prompts(title: str, scenes: list) -> list:
    """Extract visual prompts from scenes or generate from title."""
    prompts = []
    for s in scenes[:3]:
        visual = s.get("visuals") or s.get("narration", "")[:80]
        if visual:
            prompts.append(visual)

    # Pad/trim to exactly 3 prompts
    while len(prompts) < 3:
        prompts.append(f"financial growth and success, {title}")
    return prompts[:3]


def generate_fallback_video(
    title: str,
    script: str,
    scenes: list = None,
    output_path: str = "fallback.mp4",
) -> str:
    """
    Generate a slideshow-style fallback video.
    Returns output_path on success, '' on failure.
    """
    if scenes is None:
        scenes = []

    print(f"[fallback] Building Leonardo fallback video for: {title}")

    tmp_dir = tempfile.mkdtemp()
    image_paths = []
    audio_path  = os.path.join(tmp_dir, "narration.mp3")

    try:
        # 1. Generate narration audio
        print("[fallback] Generating narration audio (gTTS)...")
        if not _generate_audio(script, audio_path):
            print("[fallback] Audio generation failed")
            return ""

        audio_dur = _get_audio_duration(audio_path)
        print(f"[fallback] Audio duration: {audio_dur:.1f}s")

        # 2. Generate scene images in parallel (sequential for simplicity)
        visual_prompts = _build_visual_prompts(title, scenes)
        slide_dur = max(3.0, audio_dur / len(visual_prompts))

        print(f"[fallback] Generating {len(visual_prompts)} scene images via Leonardo...")
        for i, prompt in enumerate(visual_prompts):
            img_path = os.path.join(tmp_dir, f"slide_{i:02d}.jpg")
            ok = _generate_scene_image(prompt, img_path)
            if not ok:
                _make_color_frame(title, img_path, i)
            if not os.path.exists(img_path):
                print(f"[fallback] Slide {i+1} image missing — skipping")
                continue
            image_paths.append(img_path)
            print(f"[fallback] Slide {i+1}/{len(visual_prompts)} ready")

        if not image_paths:
            print("[fallback] No slides generated — cannot create video")
            return ""

        # 3. Build video with ffmpeg
        print("[fallback] Stitching video with ffmpeg...")
        ok = _stitch_slideshow(image_paths, audio_path, slide_dur, output_path)
        if ok:
            print(f"[fallback] Fallback video ready: {output_path}")
            return output_path
        return ""

    finally:
        # Clean up temp files (not output)
        for p in image_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.remove(audio_path)
        except OSError:
            pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _make_color_frame(title: str, output_path: str, index: int) -> None:
    """Create a solid colored frame using ffmpeg when Leonardo fails.
    No text overlay — avoids ffmpeg drawtext escaping issues with $, %, etc."""
    colors = ["0c1c48", "08091e", "1a0a2e"]
    color = colors[index % len(colors)]
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=0x{color}:size=1280x720:duration=1",
        "-vframes", "1",
        output_path,
    ], capture_output=True, timeout=15)
    if result.returncode != 0:
        print(f"[fallback] Color frame error: {result.stderr[-200:]}")


def _stitch_slideshow(
    image_paths: list,
    audio_path: str,
    slide_dur: float,
    output_path: str,
) -> bool:
    """Use ffmpeg to create a video from images + audio."""
    try:
        # Build concat filter for images
        filter_parts = []
        inputs = []
        for i, img in enumerate(image_paths):
            inputs += ["-loop", "1", "-t", str(slide_dur), "-i", img]
            filter_parts.append(f"[{i}:v]scale=1280:720,setsar=1[v{i}]")

        n = len(image_paths)
        concat_in = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")
        filter_str = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
        ] + inputs + [
            "-i", audio_path,
            "-filter_complex", filter_str,
            "-map", "[vout]",
            "-map", f"{n}:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-shortest",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"[fallback] ffmpeg error: {result.stderr[-800:]}")
            return False
        return True

    except Exception as e:
        print(f"[fallback] Stitch error: {e}")
        return False
