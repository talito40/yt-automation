# YouTube Automation Pipeline — Project Context

Fully automated YouTube video production system running on a DigitalOcean droplet. Generates and uploads daily videos to two channels using Claude (scripting), Pictory (video rendering), and YouTube Data API.

---

## Server

| | |
|---|---|
| **Host** | `165.22.33.167` |
| **User** | `root` |
| **Password** | `LukaKi2001q` |
| **OS** | Ubuntu, 1 vCPU / 1 GB RAM, NYC3 |
| **Project path** | `/opt/yt-automation/` |

**SSH:** `ssh root@165.22.33.167`
**VNC:** Connect to `165.22.33.167:5901`

---

## Git

- **Repo:** `talito40/yt-automation`
- **Active branch:** `claude/check-cronjob-status-FH03C`
- **Deploy:** `cd /opt/yt-automation && git pull`

---

## Channels

| | Channel 1 | Channel 2 |
|---|---|---|
| **Name** | Smart Money Daily | AI Advantage Daily |
| **Niche** | Personal finance | AI tools & tech |
| **Character** | ARIA (sleek AI financial analyst) | NEXUS (self-aware AI guide) |
| **Cron** | 13:00 UTC (9am EST) | 15:00 UTC (10am EST) |
| **Log** | `pipeline_ch1.log` | `pipeline_ch2.log` |
| **Token** | `youtube_token_ch1.json` | `youtube_token_ch2.json` |
| **Prompt config** | `prompt_config_ch1.json` | `prompt_config_ch2.json` |

---

## Daily Pipeline (per channel)

1. `--improve` — Research trends + evolve prompt config
2. `--run` — SEO research → script → thumbnail → Pictory video → YouTube upload → Shorts upload → Telegram notification
3. `--cleanup` — Delete videos older than 30 days with <10 views

Run scripts: `run.sh` (ch1), `run_ch2.sh` (ch2) — both in `/opt/yt-automation/`

---

## Key Modules

| Module | Purpose |
|---|---|
| `main.py` | Orchestrator + CLI (`--run`, `--improve`, `--cleanup`, `--test-email`) |
| `content_generator.py` | Claude script + metadata + Shorts |
| `prompt_improver.py` | Daily prompt evolution |
| `video_generator.py` | Pictory API |
| `youtube_uploader.py` | YouTube Data API |
| `thumbnail_generator.py` | Pillow thumbnails (1280x720) |
| `seo_researcher.py` | Topic competition scoring |
| `notifier.py` | Telegram bot (3 retries on network error) |
| `video_janitor.py` | Auto-delete underperforming videos |

---

## Notifications

Telegram bot — all pipeline events (upload success, quota warning, janitor results, test).

- **Bot token:** `8634396982:AAEIDfcdl5Dujrn8Ge37IC6wVXDawpTqiGI`
- **Chat ID:** `6345014270`

---

## VNC

TigerVNC + XFCE. Systemd service: `vncserver@1.service`

If VNC won't start after reboot:
```bash
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
vncserver -kill :1 2>/dev/null
vncserver :1 -geometry 1280x800 -depth 24 -localhost no
```

---

## Common Commands

```bash
# Check pipeline logs
tail -50 /opt/yt-automation/pipeline_ch1.log
tail -50 /opt/yt-automation/pipeline_ch2.log

# Run manually
cd /opt/yt-automation
set -a && source .env && set +a
source venv/bin/activate
python3 main.py --channel 1 --run

# Test Telegram
python3 main.py --channel 1 --test-email

# Check crontab
crontab -l

# Deploy latest code
cd /opt/yt-automation && git pull
```

---

See `FEATURES.md` for full documentation.
