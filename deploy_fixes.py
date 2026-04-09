"""Deploy all fixed files to the yt-automation droplet."""
import paramiko, os

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
BASE = "/opt/yt-automation"

# ─────────────────────────────────────────────────────────────────────────────
THUMB_GENERATOR = '''\
"""
thumb_generator.py
Generates a 1280x720 YouTube thumbnail using Pillow.
"""
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
import config

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_CHANNEL_STYLES = {
    1: {"bg": (12, 28, 72),  "accent": (255, 196, 0),   "text": (255, 255, 255)},
    2: {"bg": (8,  10, 30),  "accent": (0,   200, 255), "text": (255, 255, 255)},
}


def generate_thumbnail(title: str, output_path: str = "thumbnail.jpg") -> str:
    """Creates a 1280x720 thumbnail. Returns the absolute path."""
    W, H  = 1280, 720
    style = _CHANNEL_STYLES.get(config.CHANNEL, _CHANNEL_STYLES[1])
    bg, accent, white = style["bg"], style["accent"], style["text"]

    img  = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Subtle gradient: darker on the right
    for x in range(W):
        dim = int(60 * x / W)
        col = tuple(max(0, c - dim) for c in bg)
        draw.line([(x, 0), (x, H)], fill=col)

    # Accent stripe on left and top
    draw.rectangle([(0, 0), (14, H)], fill=accent)
    draw.rectangle([(0, 0), (W, 8)],  fill=accent)

    try:
        font_title = ImageFont.truetype(FONT_BOLD, 86)
        font_ch    = ImageFont.truetype(FONT_REG,  38)
    except OSError:
        font_title = ImageFont.load_default()
        font_ch    = ImageFont.load_default()

    wrapped = textwrap.wrap(title, width=22)[:3]
    line_h  = 96
    total_h = len(wrapped) * line_h
    y       = (H - total_h) // 2 - 20

    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        lw   = bbox[2] - bbox[0]
        x    = max(40, (W - lw) // 2)
        draw.text((x + 3, y + 3), line, font=font_title, fill=(0, 0, 0))
        draw.text((x,     y),     line, font=font_title, fill=white)
        y += line_h

    ch   = config.CHANNEL_NAME
    bbox = draw.textbbox((0, 0), ch, font=font_ch)
    draw.text((W - bbox[2] - 30, H - 60), ch, font=font_ch, fill=accent)

    abs_path = os.path.abspath(output_path)
    img.save(abs_path, "JPEG", quality=95)
    print(f"[thumb] Saved -> {abs_path}")
    return abs_path
'''

# ─────────────────────────────────────────────────────────────────────────────
CONTENT_GENERATOR = '''\
"""
content_generator.py
Uses Claude API to produce a full video package:
  - SEO topic research
  - Title, scenes, description, tags for main video
  - 60-second Shorts script
"""

import json
import anthropic
import config

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def research_seo_topic(used_topics: list[str] | None = None) -> str:
    """Uses Claude to pick a high-CTR, trending SEO topic in the channel niche."""
    used_topics = used_topics or []
    avoid = "\\n".join(f"- {t}" for t in used_topics[-30:]) if used_topics else "None yet."

    niche_guidance = {
        "personal finance": "personal finance: saving money, investing, tax strategies, budgeting, building wealth, salary negotiation",
        "AI tools and technology": "AI tools and technology: practical AI software, productivity tools, ChatGPT tips, automation, new tech",
    }.get(config.NICHE, config.NICHE)

    prompt = f"""You are an expert YouTube SEO strategist for a {niche_guidance} channel.

Pick ONE video topic that:
1. Has high search volume right now (trending or perennially popular)
2. Has strong click-through potential (pain point, money angle, or curiosity gap)
3. Can fill a compelling 6-8 minute video with actionable advice
4. Has NOT been covered yet (avoid list below)

Already covered -- do NOT repeat:
{avoid}

Reply with ONLY the topic as a single sentence. No JSON, no markdown, no quotes.
Example: How to build a 6-month emergency fund on a $50k salary in 12 months"""

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip().strip('"').strip("'")


def generate_video_package(
    used_topics: list[str] | None = None,
    seo_topic: str | None = None,
) -> dict:
    """
    Returns a dict with keys: title, script, description, tags, topic, scenes
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

    topic_directive = ""
    if seo_topic:
        topic_directive = f"\\nFocus this video on the following researched SEO topic: {seo_topic}\\n"

    prompt = f"""You are a YouTube content strategist for "{config.CHANNEL_NAME}" (niche: {niche_guidance}).
Audience: US adults aged 25-45.
{topic_directive}
IMPORTANT: Every video MUST be strictly about the niche. Do not drift.

Produce ONE complete video package optimised for maximum watch-time and ad revenue.

Rules:
- Title: 60 chars max, strong curiosity hook, no clickbait lies, include a number or year when natural
- Scenes: split into exactly 20-25 words each. Each scene needs:
    - "text": spoken words (20-25 words, plain English, no markdown)
    - "keywords": 3 short visual keywords for stock footage
- Total: ~36-40 scenes covering ~900 words
- Script tone: knowledgeable friend, NOT corporate. Hook -> 5-7 tip sections -> CTA
- Description: 3 paragraphs -- summary (with SEO keywords), timestamps placeholder, affiliate CTA
- Tags: 15 tags mixing broad and long-tail
{avoid_block}

Respond ONLY with valid JSON:
{{
  "topic": "<one-line topic summary>",
  "title": "<YouTube title>",
  "scenes": [
    {{"text": "<20-25 words>", "keywords": ["kw1", "kw2", "kw3"]}},
    ...
  ],
  "description": "<YouTube description>",
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

    chapters = "\\n\\n\\u23f1 Chapters:\\n00:00 Introduction\\n"
    affiliate_section = "\\n\\n-- Recommended Tools --\\n"
    for name, url in config.AFFILIATE_LINKS.items():
        affiliate_section += f"{name}: {url}\\n"

    package["description"] += chapters + affiliate_section
    return package


def generate_shorts_script(video_package: dict) -> dict:
    """
    Creates a punchy 60-second Short script from the main video package.
    Returns dict with keys: title, script, scenes, description, tags
    """
    main_title = video_package.get("title", "")
    main_topic = video_package.get("topic", "")
    hook_scene = ""
    if video_package.get("scenes"):
        hook_scene = video_package["scenes"][0]["text"]

    prompt = f"""You are a YouTube Shorts expert. Create a 60-second Short based on this video:

Title: {main_title}
Topic: {main_topic}
Hook: {hook_scene}

Requirements:
- Hook viewers in the FIRST 3 WORDS (must be shocking/curiosity-driving)
- Deliver ONE powerful fact or tip from the topic
- End with: "Watch the full video for [specific concrete benefit]"
- Total: 120-150 words = exactly 5-6 scenes of 20-25 words each
- Tone: urgent, punchy, no filler words

Respond ONLY with valid JSON:
{{
  "title": "<Short title, max 60 chars>",
  "scenes": [
    {{"text": "<20-25 words>", "keywords": ["kw1", "kw2", "kw3"]}},
    ...
  ],
  "description": "<2 sentences + Full video: [MAIN_VIDEO_URL]>",
  "tags": ["Shorts", "YouTubeShorts", "<niche tag 1>", "<niche tag 2>", "<topic tag>"]
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
    print("SCENES:", len(pkg.get("scenes", [])))
    shorts = generate_shorts_script(pkg)
    print("SHORT TITLE:", shorts["title"])
'''

# ─────────────────────────────────────────────────────────────────────────────
VIDEO_GENERATOR = '''\
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


def _wait_for_render_params(job_id: str, headers: dict, max_wait: int = 120) -> None:
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
'''

# ─────────────────────────────────────────────────────────────────────────────
YOUTUBE_UPLOADER = '''\
"""
youtube_uploader.py
Handles all YouTube Data API v3 operations.
"""

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
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10,
    )

    request  = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retry    = 0

    while response is None:
        try:
            print(f"[youtube] Uploading... (attempt {retry + 1})")
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"[youtube] Upload progress: {pct}%")
        except googleapiclient.errors.HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < config.MAX_RETRIES:
                retry += 1
                time.sleep(5 * retry)
            else:
                raise

    video_id = response["id"]
    url      = f"https://www.youtube.com/watch?v={video_id}"
    return url, video_id


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    service=None,
) -> tuple[str, str]:
    """
    Uploads the MP4 to YouTube as a regular video.
    Returns (video_url, video_id).
    """
    if service is None:
        service = _get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Upload complete -> {url}")
    return url, video_id


def upload_short(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    service=None,
) -> tuple[str, str]:
    """
    Uploads a vertical Short. Adds #Shorts tags automatically.
    Returns (video_url, video_id).
    """
    if service is None:
        service = _get_authenticated_service()

    short_title = title if "#Shorts" in title else f"{title} #Shorts"
    short_desc  = f"{description}\\n\\n#Shorts #YouTubeShorts"
    short_tags  = list(dict.fromkeys((tags or []) + ["Shorts", "YouTubeShorts"]))

    body = {
        "snippet": {
            "title": short_title[:100],
            "description": short_desc[:5000],
            "tags": short_tags,
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    url, video_id = _do_upload(service, body, video_path)
    print(f"[youtube] Short uploaded -> {url}")
    return url, video_id


def upload_thumbnail(service, video_id: str, thumbnail_path: str) -> bool:
    """
    Attempts to set a custom thumbnail. Returns True on success.
    Logs a warning and returns False if the channel lacks thumbnail permissions
    (requires YouTube channel verification / 1000+ subscribers).
    """
    try:
        service.thumbnails().set(
            videoId=video_id,
            media_body=googleapiclient.http.MediaFileUpload(
                thumbnail_path, mimetype="image/jpeg"
            ),
        ).execute()
        print(f"[youtube] Thumbnail set for {video_id}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"[youtube] Thumbnail skipped (channel not verified): {e.reason}")
        return False


def rename_channel(new_name: str) -> None:
    service = _get_authenticated_service()
    service.channels().update(
        part="snippet",
        body={
            "id": config.YOUTUBE_CHANNEL_ID,
            "snippet": {"title": new_name},
        },
    ).execute()
    print(f"[youtube] Channel renamed to \'{new_name}\'")


if __name__ == "__main__":
    rename_channel(config.CHANNEL_NAME)
'''

# ─────────────────────────────────────────────────────────────────────────────
MAIN_PY = '''\
"""
main.py -- YouTube Automation  |  Daily pipeline orchestrator

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
import requests
from datetime import date, datetime

# Parse --channel early so config loads the right settings
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


def run_pipeline() -> None:
    today      = date.today().isoformat()
    video_path = f"video_{today}.mp4"
    short_path = f"short_{today}.mp4"
    thumb_path = f"thumb_{today}.jpg"
    short_url  = None

    try:
        # 1 -- SEO topic research
        _log("Step 1/6 -- SEO topic research...")
        used  = _load_used_topics()
        topic = content_generator.research_seo_topic(used_topics=used)
        _log(f"  SEO topic: {topic}")

        # 2 -- Generate script and metadata
        _log("Step 2/6 -- Generating script and metadata...")
        package = content_generator.generate_video_package(used_topics=used, seo_topic=topic)
        _log(f"  Title : {package[\'title\']}")
        _log(f"  Topic : {package[\'topic\']}")

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

        # 5 -- Upload main video + try thumbnail
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

        _save_used_topic(package["topic"])

        # 6 -- Generate and upload Short (non-fatal if it fails)
        _log("Step 6/6 -- Generating and uploading Short...")
        try:
            shorts_pkg = content_generator.generate_shorts_script(package)
            shorts_pkg["description"] = shorts_pkg["description"].replace(
                "[MAIN_VIDEO_URL]", url
            )
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
            _log(f"  Short live -> {short_url}")
        except Exception as short_exc:
            _log(f"  Short failed (non-fatal): {short_exc}")

        _log(f"SUCCESS -- {url}")

        short_line = f\'\\n&#x1F3A5; Short: <a href="{short_url}">Watch</a>\' if short_url else ""
        _notify_telegram(
            f\'&#x2705; <b>{config.CHANNEL_NAME}</b>\\n\'
            f\'&#x1F4F9; <a href="{url}">{package["title"]}</a>\'
            + short_line
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
        _cleanup(video_path, short_path, thumb_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube automation pipeline")
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

# ─────────────────────────────────────────────────────────────────────────────
RUN_SH = '''\
#!/bin/bash
set -e
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python main.py --channel 1 --run
'''

RUN_CH2_SH = '''\
#!/bin/bash
set -e
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python main.py --channel 2 --run
'''

# ── Upload ────────────────────────────────────────────────────────────────────
files = {
    "thumb_generator.py":   THUMB_GENERATOR,
    "content_generator.py": CONTENT_GENERATOR,
    "video_generator.py":   VIDEO_GENERATOR,
    "youtube_uploader.py":  YOUTUBE_UPLOADER,
    "main.py":              MAIN_PY,
    "run.sh":               RUN_SH,
    "run_ch2.sh":           RUN_CH2_SH,
}

for fname, content in files.items():
    path = f"{BASE}/{fname}"
    with sftp.open(path, "w") as f:
        f.write(content)
    print(f"  uploaded {fname}")

sftp.close()

stdin, stdout, stderr = client.exec_command(
    "chmod +x /opt/yt-automation/run.sh /opt/yt-automation/run_ch2.sh"
)
stdout.read()
print("Shell scripts made executable")
client.close()
print("All done.")
