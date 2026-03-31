#!/bin/bash
# Channel 2 daily pipeline — called by cron at 20:00 UTC
cd /opt/yt-automation
set -a && source .env && set +a
source venv/bin/activate
python3 main.py --channel 2 --improve >> pipeline_ch2.log 2>&1
python3 main.py --channel 2 --run    >> pipeline_ch2.log 2>&1
python3 main.py --channel 2 --cleanup >> pipeline_ch2.log 2>&1
