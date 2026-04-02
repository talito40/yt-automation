"""
video_generator.py
Uses the Pictory API to turn a script + scenes into a rendered MP4.
Supports both 16:9 main videos and 9:16 vertical Shorts.
"""

import time
import os
import requests
import config

PICTORY_BASE = "https://api.pictory.ai/pictoryapis/v1"


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.PICTORY_API_KEY}",
        "Content-Type": "application/json",
    }


def _build_pictory_scenes(scenes: list[dict]) -> list[dict]:
    pictory_scenes = []
    for s in scenes:
        scene = {"text": s["text"], "voiceOver": True}
        if s.get("keywords"):
            scene["keywords"] = s["keywords"]
        pictory_scenes.append(scene)
    return pictory_scenes


def _split_into_scenes(script: str, words_per_scene: int = 25) -> list[dict]:
    words = script.split()
    return [
        {"text": " ".join(words[i:i + words_per_scene]), "voiceOver": True}
        for i in range(0, len(words), words_per_scene)
    ]


def _build_storyboard(
    title: str,
    script: str,
    scenes: list[dict] | None = None,
    width: str = "1920",
    height: str = "1080",
) -> dict:
    if scenes:
        pictory_scenes = _build_pictory_scenes(scenes)
    else:
        pictory_scenes = _split_into_scenes(script)

    return {
        "videoName": title[:80],
        "videoDescription": title,
        "language": "en",
        "videoWidth": width,
        "videoHeight": height,
        "scenes": pictory_scenes,
        "audio": {
            "aiVoiceOver": {"speaker": config.PICTORY_VOICE},
            "autoBackgroundMusic": True,
            "backgroundMusicVolume": 0.15,
        },
        "outro": {"brandName": config.CHANNEL_NAME},
    }


def generate_video(
    title: str,
    script: str,
    scenes: list[dict] | None = None,
    output_path: str = "output_video.mp4",
) -> str:
    """Creates a 1920x1080 main video. Returns the absolute path to the MP4."""
    return _render(title, script, scenes=scenes, output_path=output_path,
                   width="1920", height="1080")


def generate_shorts_video(
    title: str,
    script: str,
    scenes: list[dict] | None = None,
    output_path: str = "short.mp4",
) -> str:
    """Creates a 1080x1920 vertical Short. Returns the absolute path to the MP4."""
    return _render(title, script, scenes=scenes, output_path=output_path,
                   width="1080", height="1920")


def _render(
    title: str,
    script: str,
    scenes: list[dict] | None,
    output_path: str,
    width: str,
    height: str,
) -> str:
    headers = _get_headers()

    storyboard_payload = _build_storyboard(title, script, scenes=scenes,
                                           width=width, height=height)
    resp = requests.post(f"{PICTORY_BASE}/video/storyboard",
                         json=storyboard_payload, headers=headers, timeout=60)
    resp.raise_for_status()
    job_id = resp.json()["jobId"]
    print(f"[video] Storyboard created, jobId={job_id} ({width}x{height})")

    _wait_for_render_params(job_id, headers)
    resp = requests.put(f"{PICTORY_BASE}/video/render/{job_id}",
                        headers=headers, timeout=60)
    resp.raise_for_status()
    render_job_id = resp.json().get("data", {}).get("job_id", job_id)
    print(f"[video] Render started, render jobId={render_job_id}")

    video_url = _poll_until_ready(render_job_id, headers)
    return _download_video(video_url, output_path)


def _wait_for_render_params(job_id: str, headers: dict, max_wait: int = 600) -> None:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(f"{PICTORY_BASE}/jobs/{job_id}",
                            headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        if data.get("renderParams"):
            print("[video] Storyboard ready for render")
            return
        print("[video] Waiting for storyboard processing...")
        time.sleep(10)
    raise TimeoutError("Storyboard render params never appeared")


def _poll_until_ready(job_id: str, headers: dict, max_wait: int = 1200) -> str:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(f"{PICTORY_BASE}/jobs/{job_id}",
                            headers=headers, timeout=30)
        resp.raise_for_status()
        inner  = resp.json().get("data", {})
        status = (inner.get("status") or inner.get("renderStatus") or "").lower()
        print(f"[video] Render status: {status}")

        if inner.get("videoURL"):
            return inner["videoURL"]
        if status in ("failed", "error"):
            raise RuntimeError(f"Pictory render failed: {inner}")

        time.sleep(30)

    raise TimeoutError("Pictory render timed out after 20 minutes")


def _download_video(url: str, output_path: str) -> str:
    abs_path = os.path.abspath(output_path)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(abs_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    print(f"[video] Downloaded -> {abs_path} ({size_mb:.1f} MB)")
    return abs_path
