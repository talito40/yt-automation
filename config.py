import os

# ── Which channel to run (set via env var CHANNEL, default 1) ────────────────
CHANNEL = int(os.environ.get("CHANNEL", "1"))

# ── Shared API keys ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY     = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY    = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID   = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY       = os.environ.get("PICTORY_API_KEY", "")

# ── Shared settings ───────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN_FILE     = f"youtube_token_ch{CHANNEL}.json"
MAX_RETRIES            = 3

# ── Per-channel settings ──────────────────────────────────────────────────────
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
    },
}

_ch = _CHANNELS[CHANNEL]

YOUTUBE_CHANNEL_ID = _ch["youtube_channel_id"]
CHANNEL_NAME       = _ch["channel_name"]
NICHE              = _ch["niche"]
PICTORY_VOICE      = _ch["pictory_voice"]
AFFILIATE_LINKS    = _ch["affiliate_links"]
