# YouTube Automation Pipeline — Features & Documentation

Fully automated YouTube video production system. Runs daily on a schedule to research, script, render, and upload videos to two YouTube channels — with thumbnails, Shorts, notifications, and self-improving content strategy.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Daily Schedule](#daily-schedule)
- [Pipeline Steps](#pipeline-steps)
- [Channels](#channels)
- [CLI Reference](#cli-reference)
- [Modules](#modules)
- [Content Strategy](#content-strategy)
- [Notifications](#notifications)
- [Environment Variables](#environment-variables)
- [File Structure](#file-structure)
- [Setup](#setup)

---

## How It Works

```
12:00 UTC  →  --improve   Research trends + evolve prompt
13:00 UTC  →  --run       Channel 1 full pipeline
                          └─> Cleanup (delete low-view videos)

12:00 UTC  →  --improve   Channel 2 prompt improvement
20:00 UTC  →  --run       Channel 2 full pipeline
                          └─> Cleanup
```

Each daily run:
1. Researches what's trending in the niche and finds low-competition keywords
2. Generates a complete video script using a rotating set of proven retention formulas
3. Creates a custom thumbnail
4. Renders the main video via Pictory (1920x1080)
5. Generates a 20-40 second Short (1080x1920, loop-closing structure)
6. Uploads both to YouTube with optimized metadata
7. Sends a Telegram notification
8. Checks Pictory quota — warns if running low
9. Deletes any video older than 30 days with fewer than 10 views

---

## Daily Schedule

| Time (UTC) | Channel | Action |
|---|---|---|
| 12:00 | Both | Prompt improvement (trends research + formula rotation) |
| 13:00 | 1 — Smart Money Daily | Improve → Run → Cleanup |
| 20:00 | 2 — AI Advantage Daily | Improve → Run → Cleanup |

---

## Pipeline Steps

### Step 1 — SEO Topic Research
- Claude generates 8 candidate topics for the niche
- Each topic scored against YouTube search competition (via YouTube Data API)
- Lowest-competition topic selected (targets 1k–5k monthly search volume — suitable for new channels)
- Falls back to free topic selection if scoring fails
- Last 30 topics tracked to avoid repeats

### Step 2 — Content Generation
- Claude generates a complete video package: title, 36-40 scenes, description, tags
- Prompt built from: character persona + visual theme + daily-evolved strategy config
- Title: 55-60 chars, 7-10 words, proven formula (rotated daily)
- Script: ~900 words / 8-12 minute video with scene-level retention timing rules
- Description: 200-250 words with chapter timestamps placeholder + affiliate links
- Tags: 12-15 (first tag = primary keyword)

### Step 3 — Thumbnail Creation
- 1280x720px JPEG generated with Pillow (no external API)
- Per-channel color theme (navy/teal for finance, dark/purple for tech)
- Gradient background, accent bars, drop-shadowed title text, channel name
- Font: Liberation Sans (falls back through DejaVu, Ubuntu, FreeSans)

### Step 4 — Video Rendering
- Storyboard sent to Pictory API with scenes + visual keywords
- Pictory selects stock footage, adds AI voiceover, background music, outro
- Polls until render complete (max 20 min)
- Downloads final MP4

### Step 5 — Upload Main Video
- Uploaded to YouTube (10 MB chunks, resumable, 3 retries on server errors)
- Custom thumbnail set via thumbnails.set API (requires verified channel)
- Topic saved to used_topics log

### Step 6 — Generate & Upload Short
- Claude condenses full script to 4-5 scenes (20-40 sec, ~80 words)
- Loop-closing structure: final line echoes the hook word from scene 1 → triggers replays
- Pictory renders vertical (1080x1920) video
- Uploaded with #Shorts appended to title/description

### Post-Upload
- Telegram notification sent (✅ success message with title + URL)
- Twitter/X post (if credentials configured)
- Pictory quota checked — Telegram warning if ≤2 renders remain

### Cleanup (Video Janitor)
- Scans all videos on the channel
- Deletes any video that is **both** older than 30 days **and** has fewer than 10 views
- Sends Telegram notification with list of deletions (or confirms nothing deleted)

---

## Channels

### Channel 1 — Smart Money Daily
- **Niche:** Personal finance (saving, investing, tax, budgeting, wealth building)
- **Character:** ARIA — sleek AI financial analyst, calm authority, dry wit, insider-secrets voice
- **Visual theme:** Futuristic finance (holographic charts, glowing data, neon cityscapes)
- **Voice:** Matthew (Pictory)
- **Schedule:** 13:00 UTC (9 AM Eastern)
- **Affiliate links:** Robinhood, M1 Finance, Amazon

### Channel 2 — AI Advantage Daily
- **Niche:** AI tools and technology (software reviews, productivity, ChatGPT, automation)
- **Character:** NEXUS — self-aware AI guide, enthusiastic, sarcastic about hype, backstage-tour vibe
- **Visual theme:** High-tech digital (robot hands, glowing circuits, neon data streams)
- **Voice:** Joanna (Pictory)
- **Schedule:** 20:00 UTC (3 PM Eastern)
- **Affiliate links:** NordVPN, Skillshare, Amazon

---

## CLI Reference

```bash
python3 main.py --channel {1,2} [ACTION]
```

| Flag | Description |
|---|---|
| `--run` | Run the full 6-step daily pipeline |
| `--improve` | Run one prompt improvement iteration |
| `--cleanup` | Delete videos older than 30 days with <10 views |
| `--test-email` | Send a test Telegram notification |
| `--rename` | Rename the YouTube channel (one-time setup) |

**Examples:**
```bash
# Run channel 1 pipeline
python3 main.py --channel 1 --run

# Improve channel 2 prompt
python3 main.py --channel 2 --improve

# Clean up underperforming videos on channel 1
python3 main.py --channel 1 --cleanup

# Test Telegram
python3 main.py --channel 1 --test-email
```

---

## Modules

| Module | Purpose |
|---|---|
| `main.py` | Pipeline orchestrator, CLI entry point |
| `config.py` | Per-channel settings, env vars |
| `content_generator.py` | Claude script + metadata + Shorts generation |
| `prompt_improver.py` | Daily prompt evolution (trends + critique) |
| `video_generator.py` | Pictory API (render + quota check) |
| `youtube_uploader.py` | YouTube Data API (upload, thumbnail, Shorts) |
| `thumbnail_generator.py` | Pillow thumbnail creation |
| `seo_researcher.py` | Topic competition scoring via YouTube API |
| `social_poster.py` | Twitter/X post after upload |
| `notifier.py` | Telegram notifications |
| `video_janitor.py` | Auto-delete underperforming videos |
| `voice_generator.py` | ElevenLabs TTS (standalone, also embedded in Pictory) |

---

## Content Strategy

### Prompt Evolution (Daily)
Every day at 12:00 UTC, `prompt_improver.py` runs two steps:

**1. Trend Research**
Claude researches what's currently working in the niche:
- 3 trending angles (fresh, searchable, not yet oversaturated)
- 3 low-competition keywords (1k–5k monthly volume)
- 2 fresh hook techniques
- Single strategic focus for the day

**2. Output Critique**
Claude reviews the recent pipeline log and previous config:
- Voice direction: Is the character drifting generic?
- Visual direction: Are keywords producing interesting footage?
- Forbidden patterns: What's getting stale?
- Anti-template-fatigue checks (based on YouTube's January 2026 enforcement context)

**Title Formula Rotation (8 formulas, one per day):**
1. Number + Curiosity Gap
2. Contradiction / Pattern Interrupt
3. Personal Transformation + Specific Numbers
4. Stacked: Number + Stakes
5. Authority Transfer + Bold Claim
6. Regret / Wish Structure
7. Stacked: Contradiction + Curiosity Gap
8. Year + Urgency

**Narrative Structure Rotation:**
- REVERSE ENGINEERING (double-weighted — highest retention data)
- MICRO-LOOP
- MYTH-BUSTER

### Retention Engineering (Data-Backed)
Every script follows scene-level timing rules:

| Timing | Scene Rule |
|---|---|
| 0–5 sec (Scene 1) | Cold open — no greeting, start mid-claim or with result |
| 5–25 sec (Scenes 2-3) | Agitate the problem, make promise, say keyword aloud |
| 25–35 sec (Scenes 4-5) | Pattern interrupt — single 10-12 word bold statement |
| Every 6th scene | Short punchy scene (10-15 words) — retention anchor |
| 55–65% of video | Mid-roll re-engagement hook — "best part still coming" |
| Final 4 scenes | Urgency build → natural CTA (not a sales pitch) |

### Shorts Loop Structure
- Final line echoes a specific word from the opening hook
- Creates a narrative loop — viewer instinctively replays
- Replays count as full views with 3x algorithmic weight (since March 2025)

### SEO Rules
- Primary keyword spoken aloud in scenes 1-3 (YouTube indexes spoken content)
- First tag = exact primary keyword
- 200-250 word description with chapter timestamps
- Target 1k–5k monthly volume keywords (low competition for new channels)

---

## Notifications

All sent via Telegram bot.

| Event | Message |
|---|---|
| Successful upload | ✅ Channel name, title, URL, timestamp |
| Quota warning | ⚠️ Renders used/total, remaining count |
| Janitor deleted videos | 🗑️ List of deleted videos with views + age |
| Janitor — nothing deleted | ✅ Confirmation all videos healthy |
| Test | 🤖 Test message |

---

## Environment Variables

### Required

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API |
| `PICTORY_API_KEY` | Pictory video rendering |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |

### Optional (features skip silently if missing)

| Variable | Purpose |
|---|---|
| `ELEVENLABS_VOICE_ID` | Custom voice ID (default: Rachel) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID to receive notifications |
| `TWITTER_API_KEY` | Twitter/X API key |
| `TWITTER_API_SECRET` | Twitter/X API secret |
| `TWITTER_ACCESS_TOKEN` | Twitter/X access token |
| `TWITTER_ACCESS_TOKEN_SECRET` | Twitter/X access token secret |
| `NOTIFY_TO` | Notification recipient (legacy) |

---

## File Structure

```
/opt/yt-automation/
│
├── main.py                     Pipeline orchestrator + CLI
├── config.py                   Channel settings + env vars
├── content_generator.py        Script + metadata + Shorts generation
├── prompt_improver.py          Daily prompt evolution
├── video_generator.py          Pictory API integration
├── youtube_uploader.py         YouTube Data API integration
├── thumbnail_generator.py      Pillow thumbnail creation
├── seo_researcher.py           SEO topic research
├── social_poster.py            Twitter/X posting
├── notifier.py                 Telegram notifications
├── video_janitor.py            Auto-delete underperforming videos
├── voice_generator.py          ElevenLabs TTS
│
├── run.sh                      Channel 1 cron entry script
├── run_ch2.sh                  Channel 2 cron entry script
├── setup.sh                    One-time server provisioning
├── requirements.txt            Python dependencies
│
├── client_secrets.json         YouTube OAuth app secrets (not in repo)
├── .env                        API keys (not in repo)
├── venv/                       Python virtual environment
│
├── youtube_token_ch1.json      OAuth credentials — Channel 1 (generated)
├── youtube_token_ch2.json      OAuth credentials — Channel 2 (generated)
├── used_topics_ch1.json        Topic history — Channel 1 (generated)
├── used_topics_ch2.json        Topic history — Channel 2 (generated)
├── prompt_config_ch1.json      Evolved prompt config — Channel 1 (generated)
├── prompt_config_ch2.json      Evolved prompt config — Channel 2 (generated)
├── pipeline_ch1.log            Operation log — Channel 1 (generated)
└── pipeline_ch2.log            Operation log — Channel 2 (generated)
```

---

## Setup

### First-time server setup
```bash
bash setup.sh
```

This installs dependencies, creates the virtual environment, writes the `.env` template, and registers the cron jobs.

### After setup
```bash
# 1. Upload OAuth secrets
scp client_secrets.json root@YOUR_SERVER:/opt/yt-automation/

# 2. Fill in API keys
nano /opt/yt-automation/.env

# 3. Authenticate YouTube (opens browser — do this locally or via SSH tunnel)
cd /opt/yt-automation && source venv/bin/activate
python3 youtube_uploader.py  # Channel 1
CHANNEL=2 python3 youtube_uploader.py  # Channel 2

# 4. Test the pipeline
set -a && source .env && set +a
python3 main.py --channel 1 --run
```

### Updating
```bash
cd /opt/yt-automation
git pull origin claude/check-cronjob-status-FH03C
source venv/bin/activate && pip install -r requirements.txt
```
