"""Deploy traffic generation improvements to the droplet."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
# content_generator.py — Google Trends + chapters + 2-angle Shorts
# ─────────────────────────────────────────────────────────────────────────────
CONTENT_GENERATOR = '''\
"""
content_generator.py
Uses Claude API + Google Trends to produce a full video package.
"""

import json
import time
import anthropic
import config

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── Google Trends ─────────────────────────────────────────────────────────────

def get_trending_keywords() -> list[str]:
    """
    Fetches trending related queries for the channel niche from Google Trends.
    Returns up to 15 trending terms. Falls back to empty list on any error.
    """
    seed_keywords = {
        "personal finance": ["personal finance", "investing", "save money", "budget"],
        "AI tools and technology": ["AI tools", "ChatGPT", "artificial intelligence", "automation"],
    }.get(config.NICHE, [config.NICHE])

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=300, timeout=(10, 25), retries=2, backoff_factor=0.5)
        pytrends.build_payload(seed_keywords[:4], timeframe="now 7-d", geo="US")
        related = pytrends.related_queries()

        terms = []
        for kw in seed_keywords:
            top = related.get(kw, {}).get("top")
            if top is not None and not top.empty:
                terms.extend(top["query"].tolist()[:5])
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in terms:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        print(f"[trends] Found {len(unique)} trending keywords")
        return unique[:15]
    except Exception as exc:
        print(f"[trends] Could not fetch trends (non-fatal): {exc}")
        return []


# ── SEO research ──────────────────────────────────────────────────────────────

def research_seo_topic(used_topics: list[str] | None = None) -> str:
    """Uses Google Trends + Claude to pick a high-CTR, trending SEO topic."""
    used_topics  = used_topics or []
    avoid        = "\\n".join(f"- {t}" for t in used_topics[-30:]) if used_topics else "None yet."
    trending     = get_trending_keywords()
    trend_block  = ""
    if trending:
        trend_block = "\\nCurrently trending on Google (use these as inspiration):\\n" + "\\n".join(
            f"- {t}" for t in trending
        )

    niche_guidance = {
        "personal finance": "personal finance: saving money, investing, tax strategies, budgeting, building wealth, salary negotiation",
        "AI tools and technology": "AI tools and technology: practical AI software, productivity tools, ChatGPT tips, automation, new tech",
    }.get(config.NICHE, config.NICHE)

    prompt = f"""You are an expert YouTube SEO strategist for a {niche_guidance} channel.
{trend_block}

Pick ONE video topic that:
1. Aligns with trending searches above (if relevant) OR is perennially high-volume
2. Has strong click-through potential (pain point, money angle, or curiosity gap)
3. Can fill a compelling 6-8 minute video with actionable advice
4. Has NOT been covered yet (avoid list below)

Already covered -- do NOT repeat:
{avoid}

Reply with ONLY the topic as a single sentence. No JSON, no markdown, no quotes."""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip().strip(\'"\').strip("\'")


# ── Main video package ────────────────────────────────────────────────────────

def generate_video_package(
    used_topics: list[str] | None = None,
    seo_topic: str | None = None,
) -> dict:
    """
    Returns a dict with keys:
        title, script, description, tags, topic, scenes, chapters
    """
    used_topics = used_topics or []
    avoid_block = ""
    if used_topics:
        avoid_block = "\\nAvoid these already-used topics:\\n" + "\\n".join(
            f"- {t}" for t in used_topics[-30:]
        )

    niche_guidance = {
        "personal finance": "personal finance -- money saving, investing, tax strategies, budgeting, building wealth",
        "AI tools and technology": "AI tools and technology -- practical AI software reviews, productivity tools, ChatGPT tips, automation",
    }.get(config.NICHE, config.NICHE)

    topic_directive = f"\\nFocus this video on: {seo_topic}\\n" if seo_topic else ""

    prompt = f"""You are a YouTube content strategist for "{config.CHANNEL_NAME}" (niche: {niche_guidance}).
Audience: US adults aged 25-45.
{topic_directive}
IMPORTANT: Every video MUST be strictly about the niche.

Produce ONE complete video package optimised for maximum watch-time and ad revenue.

Rules:
- Title: 60 chars max, strong curiosity hook, no clickbait lies, include a number or year when natural
- Scenes: exactly 20-25 words each. Each scene:
    - "text": spoken words (plain English, no markdown)
    - "keywords": 3 short visual keywords for stock footage
- Total: ~36-40 scenes (~900 words)
- Chapters: mark where each major section starts (word index into the flat script).
  Include 5-7 chapters: Introduction + one per tip/section + Conclusion.
- Script tone: knowledgeable friend. Hook -> 5-7 tip sections -> CTA
- Description: 3 paragraphs (summary with SEO keywords, affiliate CTA)
- Tags: 15 tags mixing broad and long-tail
- Playlist: pick the single best playlist name from this list for the video:
{json.dumps(config.PLAYLISTS, indent=2)}
{avoid_block}

Respond ONLY with valid JSON:
{{
  "topic": "<one-line topic summary>",
  "title": "<YouTube title>",
  "playlist": "<playlist name from the list above>",
  "scenes": [
    {{"text": "<20-25 words>", "keywords": ["kw1", "kw2", "kw3"]}},
    ...
  ],
  "chapters": [
    {{"title": "Introduction", "start_word": 0}},
    {{"title": "<section name>", "start_word": <word index>}},
    ...
  ],
  "description": "<YouTube description (no chapters section -- added automatically)>",
  "tags": ["tag1", "tag2", ...]
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    package = json.loads(raw)

    if "scenes" in package:
        package["script"] = " ".join(s["text"] for s in package["scenes"])

    # Build chapter timestamps from word offsets (~130 wpm voiceover)
    chapters_text = _build_chapter_timestamps(package.get("chapters", []))

    affiliate_section = "\\n\\n-- Recommended Tools --\\n"
    for name, url in config.AFFILIATE_LINKS.items():
        affiliate_section += f"{name}: {url}\\n"

    package["description"] = (
        package["description"]
        + "\\n\\n\\u23f1 Chapters:\\n"
        + chapters_text
        + affiliate_section
    )

    return package


def _build_chapter_timestamps(chapters: list[dict]) -> str:
    """Convert word offsets to MM:SS timestamps at 130 wpm."""
    WPM = 130
    lines = []
    for ch in chapters:
        start_word = ch.get("start_word", 0)
        total_secs = int(start_word / WPM * 60)
        mins = total_secs // 60
        secs = total_secs % 60
        lines.append(f"{mins:02d}:{secs:02d} {ch[\'title\']}")
    return "\\n".join(lines)


# ── Shorts ────────────────────────────────────────────────────────────────────

_SHORT_ANGLES = {
    "stat":    "Lead with ONE shocking statistic or counterintuitive fact. Make it feel urgent.",
    "mistake": "Lead with the #1 mistake people make on this topic. Make them feel seen.",
    "secret":  "Lead with a little-known insider trick or loophole most people miss.",
}


def generate_shorts_script(video_package: dict, angle: str = "stat") -> dict:
    """
    Creates a punchy 60-second Short from the main video.
    angle: 'stat' | 'mistake' | 'secret'
    Returns dict with keys: title, script, scenes, description, tags
    """
    main_title = video_package.get("title", "")
    main_topic = video_package.get("topic", "")
    hook_scene = ""
    if video_package.get("scenes"):
        hook_scene = video_package["scenes"][0]["text"]

    angle_instruction = _SHORT_ANGLES.get(angle, _SHORT_ANGLES["stat"])

    prompt = f"""You are a YouTube Shorts expert. Create a 60-second Short based on this video:

Title: {main_title}
Topic: {main_topic}
Hook: {hook_scene}

Angle for THIS Short: {angle_instruction}

Requirements:
- Hook viewers in the FIRST 3 WORDS (shocking/curiosity-driving, fits the angle above)
- Deliver ONE powerful insight using the angle above
- End with: "Watch the full video for [specific concrete benefit]"
- Total: 120-150 words = exactly 5-6 scenes of 20-25 words each
- Tone: urgent, punchy, zero filler

Respond ONLY with valid JSON:
{{
  "title": "<Short title, max 55 chars>",
  "scenes": [
    {{"text": "<20-25 words>", "keywords": ["kw1", "kw2", "kw3"]}},
    ...
  ],
  "description": "<2 sentences + Full video: [MAIN_VIDEO_URL]>",
  "tags": ["Shorts", "YouTubeShorts", "<niche tag>", "<topic tag>"]
}}"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    package = json.loads(raw)
    package["script"] = " ".join(s["text"] for s in package.get("scenes", []))
    return package


if __name__ == "__main__":
    topic = research_seo_topic()
    print("SEO TOPIC:", topic)
    pkg = generate_video_package(seo_topic=topic)
    print("TITLE:", pkg["title"])
    print("PLAYLIST:", pkg.get("playlist"))
    print("CHAPTERS:", pkg.get("chapters"))
'''

# ─────────────────────────────────────────────────────────────────────────────
# youtube_uploader.py — add playlist management
# ─────────────────────────────────────────────────────────────────────────────
YOUTUBE_UPLOADER = '''\
"""
youtube_uploader.py
Handles all YouTube Data API v3 operations including playlists.
"""

import json
import os
import pickle
import time
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http
from google.auth.transport.requests import Request
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CATEGORY_ID = "27"   # Education
PRIVACY     = "public"

# Playlist ID cache file (per channel)
_PLAYLIST_CACHE_FILE = lambda: f"playlists_ch{config.CHANNEL}.json"


def _get_authenticated_service():
    credentials = None
    if os.path.exists(config.YOUTUBE_TOKEN_FILE):
        with open(config.YOUTUBE_TOKEN_FILE, "rb") as f:
            credentials = pickle.load(f)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS, SCOPES
            )
            credentials = flow.run_local_server(port=0)
        with open(config.YOUTUBE_TOKEN_FILE, "wb") as f:
            pickle.dump(credentials, f)

    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)


def _do_upload(service, body: dict, video_path: str) -> tuple[str, str]:
    """Internal upload helper. Returns (url, video_id)."""
    media = googleapiclient.http.MediaFileUpload(
        video_path, mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 10,
    )
    request  = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry    = 0

    while response is None:
        try:
            print(f"[youtube] Uploading... (attempt {retry + 1})")
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] Upload progress: {int(status.progress() * 100)}%")
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < config.MAX_RETRIES:
                retry += 1
                time.sleep(5 * retry)
            else:
                raise

    video_id = response["id"]
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def upload_video(
    video_path: str, title: str, description: str, tags: list[str], service=None,
) -> tuple[str, str]:
    """Uploads MP4 as a regular video. Returns (url, video_id)."""
    if service is None:
        service = _get_authenticated_service()
    body = {
        "snippet": {
            "title": title[:100], "description": description[:5000],
            "tags": tags[:500], "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Upload complete -> {url}")
    return url, video_id


def upload_short(
    video_path: str, title: str, description: str, tags: list[str], service=None,
) -> tuple[str, str]:
    """Uploads a vertical Short with #Shorts tags. Returns (url, video_id)."""
    if service is None:
        service = _get_authenticated_service()
    short_title = title if "#Shorts" in title else f"{title} #Shorts"
    short_desc  = f"{description}\\n\\n#Shorts #YouTubeShorts"
    short_tags  = list(dict.fromkeys((tags or []) + ["Shorts", "YouTubeShorts"]))
    body = {
        "snippet": {
            "title": short_title[:100], "description": short_desc[:5000],
            "tags": short_tags, "categoryId": CATEGORY_ID,
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Short uploaded -> {url}")
    return url, video_id


def upload_thumbnail(service, video_id: str, thumbnail_path: str) -> bool:
    """Attempts to set a custom thumbnail. Fails gracefully if not permitted."""
    try:
        service.thumbnails().set(
            videoId=video_id,
            media_body=googleapiclient.http.MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
        ).execute()
        print(f"[youtube] Thumbnail set for {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Thumbnail skipped (channel not verified): {e.reason}")
        return False


# ── Playlist management ───────────────────────────────────────────────────────

def _load_playlist_cache() -> dict:
    cache_file = _PLAYLIST_CACHE_FILE()
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    return {}


def _save_playlist_cache(cache: dict) -> None:
    with open(_PLAYLIST_CACHE_FILE(), "w") as f:
        json.dump(cache, f, indent=2)


def get_or_create_playlist(service, playlist_name: str) -> str:
    """
    Returns the playlist ID for the given name, creating it if it doesn\'t exist.
    IDs are cached locally so we don\'t spam the API.
    """
    cache = _load_playlist_cache()
    if playlist_name in cache:
        return cache[playlist_name]

    # Create new playlist
    response = service.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": playlist_name,
                "description": f"{playlist_name} | {config.CHANNEL_NAME}",
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        },
    ).execute()

    playlist_id = response["id"]
    cache[playlist_name] = playlist_id
    _save_playlist_cache(cache)
    print(f"[youtube] Created playlist \'{playlist_name}\' -> {playlist_id}")
    return playlist_id


def add_to_playlist(service, video_id: str, playlist_name: str) -> bool:
    """Adds a video to the named playlist (creates playlist if needed). Returns True on success."""
    try:
        playlist_id = get_or_create_playlist(service, playlist_name)
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"[youtube] Added {video_id} to playlist \'{playlist_name}\'")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Playlist add failed (non-fatal): {e.reason}")
        return False


def rename_channel(new_name: str) -> None:
    service = _get_authenticated_service()
    service.channels().update(
        part="snippet",
        body={"id": config.YOUTUBE_CHANNEL_ID, "snippet": {"title": new_name}},
    ).execute()
    print(f"[youtube] Channel renamed to \'{new_name}\'")


if __name__ == "__main__":
    rename_channel(config.CHANNEL_NAME)
'''

# ─────────────────────────────────────────────────────────────────────────────
# config.py — add PLAYLISTS per channel
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_PY = '''\
import os

CHANNEL = int(os.environ.get("CHANNEL", "1"))

ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY    = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID   = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY       = os.environ.get("PICTORY_API_KEY", "")

YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN_FILE     = f"youtube_token_ch{CHANNEL}.json"
MAX_RETRIES            = 3

_CHANNELS = {
    1: {
        "youtube_channel_id": "UC9k4fEX_Kg5ncM1E5rEiE3A",
        "channel_name":       "Smart Money Daily",
        "niche":              "personal finance",
        "pictory_voice":      "Matthew",
        "affiliate_links": {
            "Robinhood":  "https://robinhood.com/",
            "M1 Finance": "https://m1.com/",
            "Amazon":     "https://www.amazon.com/",
        },
        "playlists": [
            "Investing & Wealth Building",
            "Budgeting & Saving Money",
            "Tax Strategies",
            "Salary & Career Money Tips",
            "Side Hustles & Extra Income",
        ],
    },
    2: {
        "youtube_channel_id": "UCwXkcGaQFoYcR64KuOYhgbA",
        "channel_name":       "AI Advantage Daily",
        "niche":              "AI tools and technology",
        "pictory_voice":      "Joanna",
        "affiliate_links": {
            "NordVPN":    "https://nordvpn.com/",
            "Skillshare": "https://www.skillshare.com/",
            "Amazon":     "https://www.amazon.com/",
        },
        "playlists": [
            "ChatGPT Tips & Tricks",
            "AI Productivity Tools",
            "AI Tool Reviews",
            "Automation & Workflows",
            "AI for Beginners",
        ],
    },
}

_ch = _CHANNELS[CHANNEL]

YOUTUBE_CHANNEL_ID = _ch["youtube_channel_id"]
CHANNEL_NAME       = _ch["channel_name"]
NICHE              = _ch["niche"]
PICTORY_VOICE      = _ch["pictory_voice"]
AFFILIATE_LINKS    = _ch["affiliate_links"]
PLAYLISTS          = _ch["playlists"]
'''

# ─────────────────────────────────────────────────────────────────────────────
# main.py — 2 Shorts, playlists, Telegram
# ─────────────────────────────────────────────────────────────────────────────
MAIN_PY = '''\
"""
main.py -- YouTube Automation  |  Daily pipeline orchestrator

Usage:
    python main.py --channel 1 --run
    python main.py --channel 2 --run
    python main.py --channel 1 --rename
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
import config

USED_TOPICS_FILE = f"used_topics_ch{config.CHANNEL}.json"
LOG_FILE         = f"pipeline_ch{config.CHANNEL}.log"


def _log(msg: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\\n")


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


def _notify_telegram(msg: str) -> None:
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


def _upload_short(service, video_package: dict, main_url: str, angle: str, suffix: str) -> str | None:
    """Generate + upload one Short. Returns URL or None on failure."""
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


def run_pipeline() -> None:
    today      = date.today().isoformat()
    video_path = f"video_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"
    short_urls: list[str] = []

    try:
        # 1 -- SEO topic research (Google Trends + Claude)
        _log("Step 1/6 -- SEO topic research...")
        used  = _load_used_topics()
        topic = content_generator.research_seo_topic(used_topics=used)
        _log(f"  SEO topic: {topic}")

        # 2 -- Generate script and metadata
        _log("Step 2/6 -- Generating script and metadata...")
        package = content_generator.generate_video_package(used_topics=used, seo_topic=topic)
        _log(f"  Title    : {package[\'title\']}")
        _log(f"  Topic    : {package[\'topic\']}")
        _log(f"  Playlist : {package.get(\'playlist\', \'n/a\')}")

        # 3 -- Create thumbnail
        _log("Step 3/6 -- Creating thumbnail...")
        thumb_generator.generate_thumbnail(package["title"], thumb_path)

        # 4 -- Generate main video (Pictory)
        _log("Step 4/6 -- Generating main video (Pictory)...")
        video_generator.generate_video(
            title=package["title"],
            script=package["script"],
            scenes=package.get("scenes"),
            output_path=video_path,
        )

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

        _save_used_topic(package["topic"])

        # 6 -- Generate and upload 2 Shorts (different angles, both non-fatal)
        _log("Step 6/6 -- Generating and uploading Shorts (2 angles)...")
        for angle, suffix in [("stat", "a"), ("mistake", "b")]:
            short_url = _upload_short(service, package, url, angle, suffix)
            if short_url:
                _log(f"  Short ({angle}) live -> {short_url}")
                short_urls.append(short_url)

        _log(f"SUCCESS -- {url}")

        shorts_text = ""
        for i, su in enumerate(short_urls, 1):
            shorts_text += f"\\n&#x1F3A5; Short {i}: <a href=\\"{su}\\">Watch</a>"
        _notify_telegram(
            f\'&#x2705; <b>{config.CHANNEL_NAME}</b>\\n\'
            f\'&#x1F4F9; <a href="{url}">{package["title"]}</a>\'
            + shorts_text
        )

    except Exception as exc:
        _log(f"PIPELINE ERROR: {exc}")
        traceback.print_exc()
        _notify_telegram(
            f\'&#x274C; <b>{config.CHANNEL_NAME}</b> pipeline failed\\n\'
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
'''

# ── Upload all files ──────────────────────────────────────────────────────────
files = {
    "content_generator.py": CONTENT_GENERATOR,
    "youtube_uploader.py":  YOUTUBE_UPLOADER,
    "config.py":            CONFIG_PY,
    "main.py":              MAIN_PY,
}

for fname, content in files.items():
    with sftp.open(f"{BASE}/{fname}", "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

# Update crontab: 2x per channel (09:00+14:00 UTC ch1, 10:00+15:00 UTC ch2)
new_crontab = (
    "0 9  * * * /opt/yt-automation/run.sh\n"
    "0 14 * * * /opt/yt-automation/run.sh\n"
    "0 10 * * * /opt/yt-automation/run_ch2.sh\n"
    "0 15 * * * /opt/yt-automation/run_ch2.sh\n"
)
stdin, stdout, stderr = client.exec_command(
    f'echo "{new_crontab.strip()}" | crontab -'
)
stdout.read()

# Verify crontab
stdin, stdout, stderr = client.exec_command("crontab -l")
print("\nNew crontab:")
print(stdout.read().decode())

# Syntax check
checks = [
    "cd /opt/yt-automation && source venv/bin/activate && python -m py_compile content_generator.py && echo content_generator OK",
    "cd /opt/yt-automation && source venv/bin/activate && python -m py_compile youtube_uploader.py && echo youtube_uploader OK",
    "cd /opt/yt-automation && source venv/bin/activate && python -m py_compile config.py && echo config OK",
    "cd /opt/yt-automation && source venv/bin/activate && python -m py_compile main.py && echo main OK",
]
print("\nSyntax checks:")
for cmd in checks:
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(out or err or "no output")

client.close()
print("\nAll done.")
