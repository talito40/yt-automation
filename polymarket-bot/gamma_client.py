"""
gamma_client.py — Polymarket Gamma API (public, no auth required).

Provides market discovery and metadata.
API base: https://gamma-api.polymarket.com
"""

import time
import requests

import config

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"Accept": "application/json"})
    return _session


def _get(endpoint: str, params: dict | None = None) -> dict | list:
    url = config.GAMMA_API_BASE + endpoint
    for attempt in range(config.MAX_RETRIES):
        try:
            resp = _get_session().get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            raise
        except requests.exceptions.RequestException:
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Gamma API request failed after {config.MAX_RETRIES} attempts: {url}")


# ── Public interface ──────────────────────────────────────────────────────────

def get_active_markets(
    limit: int = 100,
    offset: int = 0,
    min_liquidity_usdc: float | None = None,
) -> list[dict]:
    """
    Returns active markets from the Gamma API.
    Each dict contains: id, question, description, endDate,
    liquidity, volume, outcomes (list of {name, price}).
    """
    min_liq = min_liquidity_usdc if min_liquidity_usdc is not None else config.MIN_MARKET_LIQUIDITY
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "liquidity_num_min": min_liq,
    }
    data = _get("/markets", params=params)
    if isinstance(data, dict) and "markets" in data:
        return data["markets"]
    return data if isinstance(data, list) else []


def get_market(market_id: str) -> dict:
    """Full detail for a single market."""
    return _get(f"/markets/{market_id}")


def search_markets(query: str, limit: int = 20) -> list[dict]:
    """Keyword search across market questions and descriptions."""
    data = _get("/markets", params={"search": query, "active": "true", "limit": limit})
    if isinstance(data, dict) and "markets" in data:
        return data["markets"]
    return data if isinstance(data, list) else []


def get_trending_markets(limit: int = 10) -> list[dict]:
    """Markets sorted by 24h volume descending."""
    data = _get("/markets", params={
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
    })
    if isinstance(data, dict) and "markets" in data:
        return data["markets"]
    return data if isinstance(data, list) else []


def get_events(limit: int = 50, offset: int = 0) -> list[dict]:
    """Returns top-level events (groups of related markets)."""
    data = _get("/events", params={"active": "true", "limit": limit, "offset": offset})
    if isinstance(data, dict) and "events" in data:
        return data["events"]
    return data if isinstance(data, list) else []


if __name__ == "__main__":
    print("Fetching trending markets...")
    markets = get_trending_markets(limit=5)
    for m in markets:
        print(f"  [{m.get('id', '?')}] {m.get('question', '?')[:80]}")
        print(f"    Liquidity: ${float(m.get('liquidity', 0)):,.0f}  Volume24h: ${float(m.get('volume24hr', 0)):,.0f}")
