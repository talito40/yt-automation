#!/bin/bash
# Channel 1 daily pipeline — called by cron at 14:00 UTC (9am EST)
cd /opt/yt-automation
set -a && source .env && set +a
source venv/bin/activate
python3 main.py --channel 1 --improve >> pipeline_ch1.log 2>&1
python3 main.py --channel 1 --run    >> pipeline_ch1.log 2>&1
python3 main.py --channel 1 --cleanup >> pipeline_ch1.log 2>&1
