"""
main.py — YouTube Automation  |  Daily pipeline orchestrator

Usage:
    python main.py --channel 1 --run       # Channel 1 (Smart Money Daily)
    python main.py --channel 2 --run       # Channel 2 (AI Advantage Daily)
    python main.py --channel 1 --rename    # Rename channel 1
"""

import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime

# Parse --channel early so config loads the right settings
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--channel", type=int, default=1)
_pre_args, _ = _pre.parse_known_args()
os.environ["CHANNEL"] = str(_pre_args.channel)

import content_generator
import voice_generator
import video_generator
import youtube_uploader
import thumbnail_generator
import seo_researcher
import social_poster
import config
import prompt_improver
import notifier

import config as _cfg
USED_TOPICS_FILE = f"used_topics_ch{_cfg.CHANNEL}.json"
LOG_FILE         = f"pipeline_ch{_cfg.CHANNEL}.log"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _load_used_topics() -> list[str]:
    if os.path.exists(USED_TOPICS_FILE):
        with open(USED_TOPICS_FILE) as f:
            return json.load(f)
    return []


def _save_used_topic(topic: str) -> None:
    topics = _load_used_topics()
    topics.append(topic)
    with open(USED_TOPICS_FILE, "w") as f:
        json.dump(topics, f, indent=2)


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    today = date.today().isoformat()
    video_path  = f"video_{today}.mp4"
    shorts_path = f"shorts_{today}.mp4"
    thumb_path  = f"thumbnail_{today}.jpg"

    try:
        # 1 — SEO research: find best topic
        _log("Step 1/6 — SEO topic research...")
        used = _load_used_topics()
        best_topic = seo_researcher.research_best_topic(used)
        if best_topic:
            _log(f"  SEO topic: {best_topic}")

        # 2 — Generate content
        _log("Step 2/6 — Generating script and metadata...")
        package = content_generator.generate_video_package(
            used_topics=used,
            forced_topic=best_topic,
        )
        _log(f"  Title : {package['title']}")
        _log(f"  Topic : {package['topic']}")

        # 3 — Generate thumbnail
        _log("Step 3/6 — Creating thumbnail...")
        thumbnail_generator.create_thumbnail(package["title"], thumb_path)

        # 4 — Generate main video
        _log("Step 4/6 — Generating main video (Pictory)...")
        video_generator.generate_video(
            title=package["title"],
            script=package["script"],
            scenes=package.get("scenes"),
            output_path=video_path,
        )

        # 5 — Upload main video + set thumbnail
        _log("Step 5/6 — Uploading main video...")
        url, video_id = youtube_uploader.upload_video(
            video_path=video_path,
            title=package["title"],
            description=package["description"],
            tags=package["tags"],
        )
        youtube_uploader.set_thumbnail(video_id, thumb_path)
        _save_used_topic(package["topic"])
        _log(f"  Main video live → {url}")

        # 6 — Generate + upload Short
        _log("Step 6/6 — Generating and uploading Short...")
        shorts_scenes = content_generator.generate_shorts_script(package)
        video_generator.generate_shorts_video(package["title"], shorts_scenes, shorts_path)
        shorts_url, _ = youtube_uploader.upload_shorts(
            video_path=shorts_path,
            title=package["title"],
            description=package["description"],
            tags=package["tags"],
        )
        _log(f"  Short live → {shorts_url}")

        # Notify + post to social
        notifier.send_upload_success(config.CHANNEL_NAME, package["title"], url)
        social_poster.post_to_twitter(package["title"], url, package["tags"])

        # Check Pictory quota
        quota = video_generator.check_quota()
        if quota.get("remaining") is not None:
            _log(f"Pictory quota: {quota['used']}/{quota['total']} used ({quota['remaining']} remaining)")
            if quota["remaining"] <= 2:
                notifier.send_quota_warning(quota["used"], quota["total"], quota["remaining"])

        _log(f"SUCCESS — {url}")

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        sys.exit(1)

    finally:
        _cleanup(video_path, shorts_path, thumb_path)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube automation pipeline")
    parser.add_argument("--channel", type=int, default=1, help="Channel number (1 or 2)")
    parser.add_argument("--rename",  action="store_true", help="Rename channel and exit")
    parser.add_argument("--run",     action="store_true", help="Run the daily pipeline")
    parser.add_argument("--improve",    action="store_true", help="Run one prompt improvement iteration")
    parser.add_argument("--test-email", action="store_true", help="Send a test notification email")
    args = parser.parse_args()

    if args.rename:
        youtube_uploader.rename_channel(config.CHANNEL_NAME)
    elif args.run:
        run_pipeline()
    elif args.improve:
        prompt_improver.improve()
    elif args.test_email:
        notifier.send_test(config.CHANNEL_NAME)
    else:
        parser.print_help()
