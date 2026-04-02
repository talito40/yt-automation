"""
video_stitcher.py
Splices an avatar intro clip onto the front of the main video using ffmpeg.
Both clips must be 1920x1080 MP4s (H.264/AAC) for seamless concat.
"""

import os
import subprocess
import tempfile


def splice_intro(intro_path: str, main_path: str, output_path: str) -> str:
    """
    Concatenates intro_path + main_path -> output_path.
    Re-encodes both to ensure identical stream parameters before joining.
    Returns absolute path to the stitched video.
    """
    abs_out = os.path.abspath(output_path)

    # Write a concat list file
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        tmp.write(f"file '{os.path.abspath(intro_path)}'\n")
        tmp.write(f"file '{os.path.abspath(main_path)}'\n")
        list_path = tmp.name

    try:
        # Re-encode both clips to a common profile then concat
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            abs_out,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-1000:]}")

        size_mb = os.path.getsize(abs_out) / (1024 * 1024)
        print(f"[stitch] Stitched video -> {abs_out} ({size_mb:.1f} MB)")
        return abs_out

    finally:
        os.unlink(list_path)
