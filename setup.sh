#!/bin/bash
# setup.sh — Run this once on your DigitalOcean Ubuntu server
# Usage: bash setup.sh

set -e

echo "=== Smart Money Daily — Server Setup ==="

# 1 — System deps
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git fonts-liberation

# 2 — Project dir
mkdir -p /opt/yt-automation
cd /opt/yt-automation

# 3 — Copy project files (run after uploading via scp)
# scp -r ./yt-automation/* root@YOUR_SERVER_IP:/opt/yt-automation/

# 4 — Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5 — Environment variables (fill these in)
cat > /opt/yt-automation/.env << 'ENV'
ANTHROPIC_API_KEY=your_anthropic_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
PICTORY_CLIENT_ID=your_pictory_client_id_here
PICTORY_CLIENT_SECRET=your_pictory_client_secret_here
NOTIFY_EMAIL=your_gmail_address_here
NOTIFY_APP_PASSWORD=your_gmail_app_password_here
NOTIFY_TO=lukaki.store@gmail.com
TWITTER_API_KEY=your_twitter_api_key_here
TWITTER_API_SECRET=your_twitter_api_secret_here
TWITTER_ACCESS_TOKEN=your_twitter_access_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret_here
ENV

# 6 — Load env vars on login
echo "set -a; source /opt/yt-automation/.env; set +a" >> /root/.bashrc

# 7 — Cron jobs
# 12:00 UTC — improve the prompt using yesterday's output (runs before pipeline)
(crontab -l 2>/dev/null; echo "0 12 * * * cd /opt/yt-automation && source venv/bin/activate && source .env && python main.py --channel 1 --improve >> pipeline_ch1.log 2>&1") | crontab -
(crontab -l 2>/dev/null; echo "0 12 * * * cd /opt/yt-automation && source venv/bin/activate && source .env && python main.py --channel 2 --improve >> pipeline_ch2.log 2>&1") | crontab -
# 13:00 UTC — run the daily video pipeline (9 AM Eastern)
(crontab -l 2>/dev/null; echo "0 13 * * * cd /opt/yt-automation && source venv/bin/activate && source .env && python main.py --channel 1 --run >> pipeline_ch1.log 2>&1") | crontab -
(crontab -l 2>/dev/null; echo "0 13 * * * cd /opt/yt-automation && source venv/bin/activate && source .env && python main.py --channel 2 --run >> pipeline_ch2.log 2>&1") | crontab -

echo ""
echo "=== Setup complete ==="
echo ""
echo "NEXT STEPS:"
echo "1. Upload client_secrets.json to /opt/yt-automation/"
echo "2. Edit /opt/yt-automation/.env and fill in your API keys"
echo "3. Run the one-time OAuth login:  cd /opt/yt-automation && source venv/bin/activate && python youtube_uploader.py"
echo "4. Rename the channel:            python main.py --rename"
echo "5. Test the full pipeline:        python main.py --run"
echo ""
echo "After step 3, youtube_token.json is saved and the cron job runs fully automated forever."
