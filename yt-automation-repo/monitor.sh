#!/bin/bash
cd /opt/yt-automation
set -a; source .env; set +a
source venv/bin/activate
python monitor.py
