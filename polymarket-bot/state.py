"""
state.py — Persistent bot state using a local JSON file.

Tracks open positions, trade log, and daily spend.
Mirrors the used_topics JSON approach in yt-automation.
"""

import json
import os
from datetime import datetime, timezone

import config

# ── Internal helpers ──────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_state() -> dict:
    if os.path.exists(config.STATE_FILE):
        with open(config.STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "open_positions": {},
        "trade_log": [],
        "daily_spend": {},
        "watched_markets": [],
    }


def save_state(state: dict) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Positions ─────────────────────────────────────────────────────────────────

def get_open_positions() -> dict:
    return load_state()["open_positions"]


def get_open_position_count() -> int:
    return len(get_open_positions())


def record_trade(trade: dict) -> None:
    """
    Call after a trade is placed. trade must include:
      token_id, market_id, question, side, outcome,
      entry_price, amount_usdc, order_id
    """
    state = load_state()
    token_id = trade["token_id"]
    state["open_positions"][token_id] = {
        "market_id":   trade["market_id"],
        "question":    trade.get("question", ""),
        "side":        trade["side"],
        "outcome":     trade.get("outcome", ""),
        "entry_price": trade["entry_price"],
        "amount_usdc": trade["amount_usdc"],
        "order_id":    trade["order_id"],
        "opened_at":   datetime.now(timezone.utc).isoformat(),
    }
    state["trade_log"].append({
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "action":      "OPEN",
        **{k: trade[k] for k in ("token_id", "market_id", "side", "amount_usdc", "entry_price", "order_id")},
    })
    today = _today()
    state["daily_spend"][today] = state["daily_spend"].get(today, 0.0) + trade["amount_usdc"]
    save_state(state)


def record_position_close(token_id: str, exit_price: float, reason: str = "manual") -> None:
    state = load_state()
    position = state["open_positions"].pop(token_id, None)
    if position:
        pnl = (exit_price - position["entry_price"]) * (position["amount_usdc"] / position["entry_price"])
        state["trade_log"].append({
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "action":      "CLOSE",
            "token_id":    token_id,
            "market_id":   position["market_id"],
            "entry_price": position["entry_price"],
            "exit_price":  exit_price,
            "amount_usdc": position["amount_usdc"],
            "pnl_usdc":    round(pnl, 4),
            "reason":      reason,
        })
    save_state(state)


def is_position_open(token_id: str) -> bool:
    return token_id in load_state()["open_positions"]


# ── Daily spend ───────────────────────────────────────────────────────────────

def get_daily_spend(date_str: str | None = None) -> float:
    date_str = date_str or _today()
    return load_state()["daily_spend"].get(date_str, 0.0)


# ── Trade log ─────────────────────────────────────────────────────────────────

def get_trade_log(last_n: int = 50) -> list:
    return load_state()["trade_log"][-last_n:]


# ── Watched markets ───────────────────────────────────────────────────────────

def add_watched_market(market_id: str) -> None:
    state = load_state()
    if market_id not in state["watched_markets"]:
        state["watched_markets"].append(market_id)
        save_state(state)


def remove_watched_market(market_id: str) -> None:
    state = load_state()
    state["watched_markets"] = [m for m in state["watched_markets"] if m != market_id]
    save_state(state)


def get_watched_markets() -> list:
    return load_state()["watched_markets"]


if __name__ == "__main__":
    s = load_state()
    print("Open positions:", len(s["open_positions"]))
    print("Daily spend today:", get_daily_spend())
    print("Trade log entries:", len(s["trade_log"]))
    print("Watched markets:", s["watched_markets"])
