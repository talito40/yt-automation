#!/bin/bash
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python main.py --channel 1 --run || true
python validate.py --channel 1
