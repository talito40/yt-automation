"""
main.py -- YouTube Automation  |  Daily pipeline orchestrator
HeyGen generates ALL videos (main + Shorts). Pictory removed entirely.
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
import youtube_uploader
import thumb_generator
import avatar_generator
import leonardo_fallback
import config

USED_TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE         = f"pipeline_ch{config.CHANNEL}.log"


def _log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
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


def _notify(msg):
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


def _generate_heygen(title, script, scenes, output_path):
    """Generate a video via HeyGen. Returns path on success, '' on failure."""
    full_script = script
    if not full_script and scenes:
        full_script = " ".join(s.get("narration", "") for s in scenes).strip()
    return avatar_generator.generate_intro_clip(
        video_title=title,
        script=full_script,
        scenes=scenes,
        output_path=output_path,
    )


def _upload_short(service, package, main_url, angle, suffix):
    today      = date.today().isoformat()
    short_path = f"short_{today}_{suffix}.mp4"
    try:
        topic = package.get("topic", package.get("title", config.NICHE))
        shorts_pkg = content_generator.generate_shorts_script(topic, config.NICHE, angle=angle)
        shorts_pkg["description"] = shorts_pkg.get("description", "").replace("[MAIN_VIDEO_URL]", main_url)

        _log(f"  Generating Short ({angle}) via HeyGen...")
        result = _generate_heygen(
            title=shorts_pkg["title"],
            script=shorts_pkg.get("script", ""),
            scenes=[],
            output_path=short_path,
        )
        if not result:
            _log(f"  Short ({angle}) HeyGen failed — skipping")
            return None, None

        short_url, short_id = youtube_uploader.upload_short(
            video_path=short_path,
            title=shorts_pkg["title"],
            description=shorts_pkg.get("description", ""),
            tags=shorts_pkg.get("tags", []),
            service=service,
        )
        return short_url, shorts_pkg["title"]
    except Exception as exc:
        _log(f"  Short ({angle}) failed (non-fatal): {exc}")
        return None, None
    finally:
        _cleanup(short_path)


def run_pipeline():
    today      = date.today().isoformat()
    video_path = f"video_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"

    try:
        # ── Step 1: SEO topic research ─────────────────────────────────────────
        _log("Step 1/5 -- SEO topic research...")
        keywords = content_generator.get_trending_keywords(config.NICHE)
        seo_data = content_generator.research_seo_topic(config.NICHE, keywords)
        topic    = seo_data.get("topic", config.NICHE)
        _log(f"  SEO topic: {topic}")

        # ── Step 2: Generate script and metadata ───────────────────────────────
        _log("Step 2/5 -- Generating script and metadata...")
        package = content_generator.generate_video_package(topic, config.NICHE)
        if "topic" not in package:
            package["topic"] = topic
        if "script" not in package:
            scenes = package.get("scenes", [])
            package["script"] = " ".join(
                s.get("narration", "") for s in scenes
            ).strip() if scenes else topic

        script_len = len(package["script"])
        _log(f"  Title    : {package['title']}")
        _log(f"  Topic    : {package['topic']}")
        _log(f"  Script   : {script_len} chars")
        _log(f"  Playlist : {package.get('playlist', 'n/a')}")
        _log(f"  Avatar   : {config.HEYGEN_AVATAR_ID}")

        # ── Step 3: Create thumbnail ───────────────────────────────────────────
        _log("Step 3/5 -- Creating thumbnail...")
        thumb_generator.generate_thumbnail(package["title"], thumb_path)

        # ── Step 4: Generate main video (HeyGen primary, Leonardo fallback) ──────
        _log("Step 4/5 -- Generating presenter video (HeyGen)...")
        result = _generate_heygen(
            title=package["title"],
            script=package.get("script", ""),
            scenes=package.get("scenes", []),
            output_path=video_path,
        )
        if result:
            _log(f"  HeyGen SUCCESS — presenter video ready")
        else:
            _log("  HeyGen failed — trying Leonardo slideshow fallback...")
            result = leonardo_fallback.generate_fallback_video(
                title=package["title"],
                script=package.get("script", ""),
                scenes=package.get("scenes", []),
                output_path=video_path,
            )
            if result:
                _log("  Leonardo fallback video ready")
            else:
                raise RuntimeError("Both HeyGen and Leonardo fallback failed")

        _log(f"  Presenter video ready ({os.path.getsize(video_path)//1024//1024} MB)")

        # ── Step 5: Upload ─────────────────────────────────────────────────────
        _log("Step 5/5 -- Uploading main video...")
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

        is_heygen = os.path.exists(video_path) and result == video_path
        source_tag = f"HeyGen ({config.HEYGEN_AVATAR_ID})" if avatar_generator.HEYGEN_API_KEY else "Leonardo slideshow"
        _notify(
            f"\U0001f4f9 <b>{config.CHANNEL_NAME}</b> \u2014 New video live!\n"
            f"\U0001f3ac <a href=\"{url}\">{package['title']}</a>\n"
            f"\U0001f916 Source: {source_tag}\n"
            f"\U0001f4cb Playlist: {playlist_name or 'None'}"
        )

        try:
            recent = youtube_uploader.get_recent_videos(service, exclude_id=video_id, max_results=3)
            youtube_uploader.post_channel_comment(service, video_id, recent)
        except Exception as e:
            _log(f"  Comment failed (non-fatal): {e}")

        try:
            youtube_uploader.update_older_descriptions(service, package["title"], url, max_videos=3)
        except Exception as e:
            _log(f"  Description update failed (non-fatal): {e}")

        _save_used_topic(package["topic"])

        # ── Shorts ─────────────────────────────────────────────────────────────
        _log("Generating Shorts (2 angles)...")
        for angle, suffix in [("stat", "a"), ("mistake", "b")]:
            short_url, short_title = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                _notify(
                    f"\u26a1 <b>{config.CHANNEL_NAME}</b> \u2014 New Short live!\n"
                    f"<a href=\"{short_url}\">{short_title}</a>\n"
                    f"\U0001f517 Main: <a href=\"{url}\">Watch</a>"
                )

        _log(f"SUCCESS -- {url}")

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify(
            f"\u274c <b>{config.CHANNEL_NAME}</b> pipeline failed\n"
            f"Error: {exc}"
        )
        sys.exit(1)

    finally:
        _cleanup(video_path, thumb_path)


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
