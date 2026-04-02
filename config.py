import os

CHANNEL = int(os.environ.get("CHANNEL", "1"))

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
PICTORY_API_KEY     = os.environ.get("PICTORY_API_KEY", "")
HEYGEN_API_KEY      = os.environ.get("HEYGEN_API_KEY", "")
LEONARDO_API_KEY    = os.environ.get("LEONARDO_API_KEY", "")

# HeyGen stock avatar IDs (no photo upload needed)
_HEYGEN_AVATARS = {
    1: "Albert_public_1",                             # Albert – light blue blazer, friendly/trustworthy
    2: "Annie_Business_Casual_Standing_Front_public", # Annie  – grey blazer, tech office background
}
HEYGEN_AVATAR_ID = _HEYGEN_AVATARS.get(CHANNEL, "Albert_public_1")

_HEYGEN_VOICES = {
    1: "en-US-GuyNeural",
    2: "en-US-AriaNeural",
}
HEYGEN_VOICE_ID = _HEYGEN_VOICES.get(CHANNEL, "en-US-GuyNeural")

_HEYGEN_BG = {
    1: "#0c1c48",
    2: "#08091e",
}
HEYGEN_BG_COLOR = _HEYGEN_BG.get(CHANNEL, "#0c1c48")

# Legacy – kept so old references don't break, but no longer used by avatar_generator
PRESENTER_PHOTO = f"presenter_ch{CHANNEL}.jpg"

YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN_FILE     = f"youtube_token_ch{CHANNEL}.json"
MAX_RETRIES            = 3

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
        "playlists": [
            "Investing & Wealth Building",
            "Budgeting & Saving Money",
            "Tax Strategies",
            "Salary & Career Money Tips",
            "Side Hustles & Extra Income",
        ],
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
        "playlists": [
            "ChatGPT Tips & Tricks",
            "AI Productivity Tools",
            "AI Tool Reviews",
            "Automation & Workflows",
            "AI for Beginners",
        ],
    },
}

_ch = _CHANNELS[CHANNEL]

YOUTUBE_CHANNEL_ID = _ch["youtube_channel_id"]
CHANNEL_NAME       = _ch["channel_name"]
NICHE              = _ch["niche"]
PICTORY_VOICE      = _ch["pictory_voice"]
AFFILIATE_LINKS    = _ch["affiliate_links"]
PLAYLISTS          = _ch["playlists"]
