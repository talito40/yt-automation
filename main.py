"""
main.py -- YouTube Automation  |  Daily pipeline orchestrator
"""

import argparse
import json
import os
import sys
import traceback
import requests
from datetime import date, datetime

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--channel", type=int, default=1)
_pre_args, _ = _pre.parse_known_args()
os.environ["CHANNEL"] = str(_pre_args.channel)

import content_generator
import video_generator
import youtube_uploader
import thumb_generator
import avatar_generator
import video_stitcher
import config

USED_TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE         = f"pipeline_ch{config.CHANNEL}.log"


def _log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _load_used_topics():
    if os.path.exists(USED_TOPICS_FILE):
        with open(USED_TOPICS_FILE) as f:
            return json.load(f)
    return []


def _save_used_topic(topic):
    topics = _load_used_topics()
    topics.append(topic)
    with open(USED_TOPICS_FILE, "w") as f:
        json.dump(topics, f, indent=2)


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _notify_telegram(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def _upload_short(service, video_package, main_url, angle, suffix):
    today      = date.today().isoformat()
    short_path = f"short_{today}_{suffix}.mp4"
    try:
        shorts_pkg = content_generator.generate_shorts_script(video_package, angle=angle)
        shorts_pkg["description"] = shorts_pkg["description"].replace("[MAIN_VIDEO_URL]", main_url)
        video_generator.generate_shorts_video(
            title=shorts_pkg["title"],
            script=shorts_pkg["script"],
            scenes=shorts_pkg.get("scenes"),
            output_path=short_path,
        )
        short_url, _ = youtube_uploader.upload_short(
            video_path=short_path,
            title=shorts_pkg["title"],
            description=shorts_pkg["description"],
            tags=shorts_pkg.get("tags", []),
            service=service,
        )
        return short_url
    except Exception as exc:
        _log(f"  Short ({angle}) failed (non-fatal): {exc}")
        return None
    finally:
        _cleanup(short_path)


def run_pipeline():
    today      = date.today().isoformat()
    raw_path   = f"video_raw_{today}.mp4"
    video_path = f"video_{today}.mp4"
    intro_path = f"intro_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"
    short_urls = []

    try:
        # 1 -- SEO topic research
        _log("Step 1/6 -- SEO topic research...")
        used  = _load_used_topics()
        topic = content_generator.research_seo_topic(used_topics=used)
        _log(f"  SEO topic: {topic}")

        # 2 -- Generate script and metadata
        _log("Step 2/6 -- Generating script and metadata...")
        package = content_generator.generate_video_package(used_topics=used, seo_topic=topic)
        _log(f"  Title    : {package['title']}")
        _log(f"  Topic    : {package['topic']}")
        _log(f"  Playlist : {package.get('playlist', 'n/a')}")

        # 3 -- Create thumbnail
        _log("Step 3/6 -- Creating thumbnail...")
        thumb_generator.generate_thumbnail(package["title"], thumb_path)

        # 4 -- Generate main video (Pictory)
        _log("Step 4/6 -- Generating main video (Pictory)...")
        video_generator.generate_video(
            title=package["title"],
            script=package["script"],
            scenes=package.get("scenes"),
            output_path=raw_path,
        )

        # 4b -- Avatar intro (HeyGen)
        _log("Step 4b/6 -- Generating avatar intro (HeyGen)...")
        intro = avatar_generator.generate_intro_clip(
            video_title=package["title"],
            photo_path=config.PRESENTER_PHOTO,
            output_path=intro_path,
        )

        # 4c -- Stitch
        if intro:
            _log("Step 4c/6 -- Stitching intro onto main video...")
            try:
                video_stitcher.splice_intro(intro_path, raw_path, video_path)
                _log("  Intro stitched successfully")
            except Exception as e:
                _log(f"  Stitch failed (non-fatal): {e}")
                os.rename(raw_path, video_path)
        else:
            _log("  No intro -- using raw Pictory video")
            os.rename(raw_path, video_path)

        # 5 -- Upload main video + thumbnail + playlist
        _log("Step 5/6 -- Uploading main video...")
        service = youtube_uploader._get_authenticated_service()
        url, video_id = youtube_uploader.upload_video(
            video_path=video_path,
            title=package["title"],
            description=package["description"],
            tags=package["tags"],
            service=service,
        )
        _log(f"  Main video live -> {url}")
        youtube_uploader.upload_thumbnail(service, video_id, thumb_path)

        playlist_name = package.get("playlist")
        if playlist_name:
            youtube_uploader.add_to_playlist(service, video_id, playlist_name)

        # 5b -- Post channel comment with links to related videos
        _log("  Posting channel comment with related video links...")
        recent = youtube_uploader.get_recent_videos(service, exclude_id=video_id, max_results=3)
        youtube_uploader.post_channel_comment(service, video_id, recent)

        # 5c -- Update older video descriptions with link to this new video
        _log("  Updating older video descriptions with link to new video...")
        youtube_uploader.update_older_descriptions(service, package["title"], url, max_videos=3)

        _save_used_topic(package["topic"])

        # 6 -- 2 Shorts
        _log("Step 6/6 -- Generating and uploading Shorts (2 angles)...")
        for angle, suffix in [("stat", "a"), ("mistake", "b")]:
            short_url = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                short_urls.append(short_url)

        _log(f"SUCCESS -- {url}")

        shorts_text = ""
        for i, su in enumerate(short_urls, 1):
            shorts_text += f"\n🎥 Short {i}: <a href=\"{su}\">Watch</a>"
        avatar_line = "\n🤖 Avatar intro: ON" if intro else "\n🤖 Avatar intro: OFF"
        _notify_telegram(
            f"✅ <b>{config.CHANNEL_NAME}</b>\n"
            f"📹 <a href=\"{url}\">{package['title']}</a>"
            + avatar_line + shorts_text
        )

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify_telegram(
            f"❌ <b>{config.CHANNEL_NAME}</b> pipeline failed\n"
            f"Error: {exc}"
        )
        sys.exit(1)

    finally:
        _cleanup(raw_path, video_path, intro_path, thumb_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--rename",  action="store_true")
    parser.add_argument("--run",     action="store_true")
    args = parser.parse_args()

    if args.rename:
        youtube_uploader.rename_channel(config.CHANNEL_NAME)
    elif args.run:
        run_pipeline()
    else:
        parser.print_help()
