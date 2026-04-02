import os
from dotenv import load_dotenv

load_dotenv()

# ── Polymarket / CLOB ─────────────────────────────────────────────────────────
POLY_PRIVATE_KEY    = os.environ.get("POLY_PRIVATE_KEY", "")
POLY_API_KEY        = os.environ.get("POLY_API_KEY", "")
POLY_API_SECRET     = os.environ.get("POLY_API_SECRET", "")
POLY_API_PASSPHRASE = os.environ.get("POLY_API_PASSPHRASE", "")
POLY_CHAIN_ID       = int(os.environ.get("POLY_CHAIN_ID", "137"))  # Polygon mainnet

# ── API base URLs ─────────────────────────────────────────────────────────────
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE  = "https://clob.polymarket.com"
CLOB_WS_URL    = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# ── AI ────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
AI_TRIAGE_MODEL        = "claude-haiku-4-5-20251001"   # fast + cheap: batch triage
AI_ANALYSIS_MODEL      = "claude-sonnet-4-6"           # quality: deep market analysis

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Trading guardrails ────────────────────────────────────────────────────────
MAX_POSITION_USDC      = float(os.environ.get("MAX_POSITION_USDC", "50"))
MAX_OPEN_POSITIONS     = int(os.environ.get("MAX_OPEN_POSITIONS", "5"))
MAX_DAILY_SPEND_USDC   = float(os.environ.get("MAX_DAILY_SPEND_USDC", "200"))
MIN_CONFIDENCE_SCORE   = int(os.environ.get("MIN_CONFIDENCE_SCORE", "7"))

# ── Monitoring ────────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS  = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
USE_WEBSOCKET          = os.environ.get("USE_WEBSOCKET", "false").lower() == "true"
SIGNIFICANT_MOVE_PCT   = float(os.environ.get("SIGNIFICANT_MOVE_PCT", "5.0"))
MIN_MARKET_LIQUIDITY   = float(os.environ.get("MIN_MARKET_LIQUIDITY", "1000.0"))
TRIAGE_INTEREST_THRESHOLD = int(os.environ.get("TRIAGE_INTEREST_THRESHOLD", "6"))

# ── Misc ──────────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
LOG_FILE    = "logs/polymarket_bot.log"
STATE_FILE  = "bot_state.json"
