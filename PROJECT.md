# YT Automation — Project Documentation

## Overview

Fully automated YouTube publishing pipeline that runs daily on a DigitalOcean droplet. Each run generates a topic, writes a script, creates a thumbnail, generates a presenter video, and uploads everything to YouTube — without any manual intervention.

Two channels are operated in parallel:
- **Channel 1** — Smart Money Daily (personal finance niche)
- **Channel 2** — AI Advantage Daily (AI tools/tech niche)

---

## Repository

- **GitHub**: https://github.com/talito40/yt-automation (branch: `master`)
- **Local**: `C:\Users\TVARKEL\Documents\claude-stuff\project5\`
- **Secrets excluded from git**: `.env`, `client_secrets.json`, `youtube_token_ch*.json`, `for-yt-automation/`

---

## Infrastructure

| Component | Details |
|---|---|
| Server | DigitalOcean droplet, IP `165.22.33.167` |
| User | `root` |
| Working directory | `/opt/yt-automation/` |
| Python env | `/opt/yt-automation/venv/` |
| Env vars | `/opt/yt-automation/.env` (sourced by run.sh) |
| Cron | Ch1 at `45 11 * * *`, Ch2 at `45 12 * * *` UTC |
| Monitor | `*/10 * * * *` via `monitor.sh` |

**IMPORTANT:** `run.sh` and `run_ch2.sh` are deployed via SFTP which creates files as 644 (no execute bit). Crontab uses `bash /opt/yt-automation/run.sh` explicitly — never `./run.sh`.

---

## API Keys & Services

| Service | Key location | Status |
|---|---|---|
| Anthropic (Claude) | `.env` → `ANTHROPIC_API_KEY` | Active |
| HeyGen | `.env` → `HEYGEN_API_KEY` | Active — primary video generator |
| Leonardo.ai | `.env` → `LEONARDO_API_KEY` = `03bc47f5-2368-4a26-be70-bca0f25c46a7` | Active — fallback + thumbnails |
| YouTube Data API | `client_secrets.json` + `youtube_token_ch{1,2}.json` | Active |
| Telegram | `.env` → `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Active — pipeline notifications |
| ElevenLabs | `.env` → `ELEVENLABS_API_KEY` | **Safe to cancel** — never called by pipeline |
| Pictory.ai | `.env` → `PICTORY_API_KEY` | **Cancelled/expired** — returns 403, removed from code |

---

## Pipeline Flow (`main.py`)

```
Step 1/5  SEO topic research     content_generator.py (pytrends → Anthropic fallback)
Step 2/5  Script + metadata      content_generator.py → Anthropic API
Step 3/5  Thumbnail              thumb_generator.py → Leonardo.ai (Pillow fallback)
Step 4/5  Presenter video        avatar_generator.py → HeyGen PRIMARY
                                     └─ on failure → leonardo_fallback.py FALLBACK
Step 5/5  Upload + Shorts        youtube_uploader.py + 2x HeyGen Shorts
```

Notifications sent via Telegram at pipeline SUCCESS and ERROR.

---

## Key Files

### `main.py`
- Entry point. Called via `python main.py --channel 1 --run`
- `_log()` uses `flush=True` for real-time output in nohup logs
- Steps 1-5 as above; Shorts generated after main upload

### `config.py`
Daily avatar rotation — avatar changes every day using ordinal date modulo pool size:
```python
_day = date.today().toordinal()
HEYGEN_AVATAR_ID = _pool[_day % len(_pool)]
```
- **Ch1 pool** (6 Albert outfits): `Albert_public_1` through `Albert_public_6`
- **Ch2 pool** (10 Annie outfits): `Annie_expressive_public`, `Annie_expressive2_public`, `Annie_expressive4_public`, `Annie_expressive5_public`, `Annie_expressive6_public`, `Annie_expressive7_public`, `Annie_expressive8_public`, `Annie_expressive10_public`, `Annie_expressive11_public`, `Annie_expressive12_public`

HeyGen voice IDs (real format, not Azure):
- Ch1 James: `8a8fb6db01a44463a087e68f54d0870b-f4ffc86b-6040-428f-b71f-d1244273c488`
- Ch2 Cassidy: `16a09e4706f74997ba4ed05ea11470f6`

### `content_generator.py`
Script length kept short (1,400–1,700 chars) to ensure HeyGen generates within time limits:
- 3 scenes total, 300–400 words
- Scene 1: hook 60–80 words
- Scene 2: points 1–2, 120–150 words
- Scene 3: points 3–4 + CTA, 120–150 words
- `max_tokens=2000`

### `avatar_generator.py`
```python
MAX_CHARS_PER_CHUNK = 3000
POLL_INTERVAL       = 15      # seconds
MAX_POLL_ATTEMPTS   = 160     # 160 * 15s = 40 minutes max
```
Submits script to HeyGen v2 API, polls until `completed` or timeout. On timeout/failure returns `""` so main.py triggers the fallback.

### `leonardo_fallback.py`
Slideshow fallback when HeyGen fails:
1. gTTS narration audio from script
2. 3 Leonardo scene images at **1280×720** (Phoenix model `de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3`)
3. ffmpeg concat: `scale=1280:720`, `-preset veryfast`, `timeout=600`
4. Color frame fallback if Leonardo also fails (no `drawtext` — breaks on `$` in titles)

### `thumb_generator.py`
Leonardo.ai thumbnail at 1280×720. Channel-specific prompts:
- Ch1: Mark Tilbury style, navy/gold, finance aesthetic
- Ch2: futuristic tech, neon cyan/dark blue

### `monitor.py`
Per-video view tracking. Runs every 10 minutes (`*/10 * * * *`). Reduced from 1-min to avoid hitting YouTube API 10,000 unit/day quota.

### `validate.py`
Pre-flight checks run before each pipeline. Detects last run status by searching for both `"Step 1/5"` (current) and `"Step 1/6"` (legacy) in logs.

---

## HeyGen Notes

- **Credit system**: each video costs ~5 credits. Monitor balance at app.heygen.com
- **Generation time**: normally 5–10 min for a 2–3 min video; can be 20–40 min when queue is congested
- **Queue congestion**: submitting many jobs in quick succession (e.g. debugging runs) backs up their queue. Credits are consumed even on timeout/failure if the job started processing
- **Stock avatars**: only `_public` variants work with API keys (non-custom plan)
- **Voice ID format**: HeyGen uses its own UUID format — NOT Azure `en-US-GuyNeural` style

---

## Leonardo.ai Notes

- **Max width**: 1536px. Anything wider rejected
- **Valid dimensions**: not all arbitrary sizes accepted. Use 1280×720 (confirmed working)
- **Model**: Phoenix 1.0 (`de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3`)
- **API key**: `03bc47f5-2368-4a26-be70-bca0f25c46a7`

---

## ffmpeg Notes

- `drawtext` filter breaks on `$` in titles (treated as variable prefix) — never use text overlays in fallback
- Color frames use solid `ffmpeg -f lavfi -i color=...` with no text
- Encoding: always use `-preset veryfast` and `timeout=600` for slideshow videos

---

## Deployment Pattern

All local edits live in `C:\Users\TVARKEL\Documents\claude-stuff\project5\`. Deployment scripts (`deploy_*.py`) use paramiko SFTP to upload to the server.

To deploy a single file manually:
```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('165.22.33.167', username='root', password='LukaKi2001q', timeout=10)
sftp = client.open_sftp()
with open('local_file.py', 'r') as f:
    content = f.read()
with sftp.open('/opt/yt-automation/local_file.py', 'w') as f:
    f.write(content)
sftp.close()
client.close()
```

Always syntax-check after deploy:
```bash
cd /opt/yt-automation && source venv/bin/activate && python -m py_compile file.py && echo OK
```

---

## Triggering Pipelines Manually

```bash
# Ch1
nohup bash /opt/yt-automation/run.sh > /tmp/run_ch1_manual.log 2>&1 &

# Ch2
nohup bash /opt/yt-automation/run_ch2.sh > /tmp/run_ch2_manual.log 2>&1 &
```

Monitor with:
```bash
tail -f /tmp/run_ch1_manual.log
grep -E "Step|ERROR|SUCCESS|live ->" /tmp/run_ch1_manual.log
```

---

## Known Issues & Fixes Applied

| Issue | Fix |
|---|---|
| HeyGen voice IDs in Azure format (`en-US-GuyNeural`) | Changed to real HeyGen UUIDs in config.py |
| `run.sh` loses execute bit on SFTP deploy | Crontab uses `bash run.sh` not `./run.sh` |
| Monitor hit YouTube API quota (1-min frequency) | Reduced to `*/10 * * * *` |
| HeyGen scripts 8,200 chars → 20-min generation | Reduced to 3 scenes, ~1,500 chars |
| HeyGen credit exhaustion | Top up at app.heygen.com; ~5 credits per video |
| Pictory 403 Forbidden | Subscription expired; fully removed from pipeline |
| Leonardo fallback width 1920px | Capped at 1280px (max 1536, but 1280×720 confirmed) |
| ffmpeg `drawtext` breaks on `$` in titles | Removed text overlay; solid color frames only |
| ffmpeg scale to 1920×1080 from 1280×720 source | Changed to `scale=1280:720` |
| ffmpeg `timeout=120` too short for 130–150s video | Increased to `timeout=600` |
| HeyGen 20-min polling timeout too short | Increased `MAX_POLL_ATTEMPTS` from 80 to 160 (40 min) |
| `validate.py` detects `Step 1/6` but pipeline uses `Step 1/5` | Fixed to detect both patterns |
| Python stdout buffering in nohup logs | Added `flush=True` to `_log()` in main.py |

---

## Channel Info

| | Ch1 | Ch2 |
|---|---|---|
| Name | Smart Money Daily | AI Advantage Daily |
| YouTube ID | `UC9k4fEX_Kg5ncM1E5rEiE3A` | `UCwXkcGaQFoYcR64KuOYhgbA` |
| Niche | Personal finance | AI tools & technology |
| Presenter | Albert (6 outfits) | Annie (10 outfits) |
| Voice | James | Cassidy |
| Token file | `youtube_token_ch1.json` | `youtube_token_ch2.json` |
