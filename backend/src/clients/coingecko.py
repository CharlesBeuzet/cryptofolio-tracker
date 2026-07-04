"""CoinGecko market chart client with in-memory caching (no DB persistence)."""
from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config.loader import get_section

# Common portfolio symbols → CoinGecko coin ids
DEFAULT_SYMBOL_IDS: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "ARB": "arbitrum",
    "OP": "optimism",
    "USDT": "tether",
    "USDC": "usd-coin",
}

_cache: Dict[Tuple[str, int], Tuple[float, List[Dict[str, Any]]]] = {}
_coin_list_cache: Optional[Tuple[float, Dict[str, str]]] = None


def _coingecko_config() -> Dict[str, Any]:
    return get_section("coingecko")


def _base_url() -> str:
    return str(_coingecko_config().get("base_url") or "https://api.coingecko.com/api/v3").rstrip("/")


def _cache_ttl() -> int:
    return int(_coingecko_config().get("cache_ttl_seconds") or 300)


def _is_mock_enabled() -> bool:
    return bool(_coingecko_config().get("mock"))


def _api_headers() -> Dict[str, str]:
    api_key = _coingecko_config().get("api_key")
    if api_key:
        return {"x-cg-pro-api-key": str(api_key)}
    return {}


def _symbol_map() -> Dict[str, str]:
    merged = dict(DEFAULT_SYMBOL_IDS)
    overrides = _coingecko_config().get("symbol_ids") or {}
    for symbol, coin_id in overrides.items():
        merged[str(symbol).upper()] = str(coin_id)
    return merged


async def _resolve_coin_id(symbol: str) -> Optional[str]:
    upper = symbol.upper()
    mapping = _symbol_map()
    if upper in mapping:
        return mapping[upper]

    global _coin_list_cache
    now = time.monotonic()
    if _coin_list_cache is None or now - _coin_list_cache[0] > 86_400:
        url = f"{_base_url()}/coins/list"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=_api_headers())
            response.raise_for_status()
            rows = response.json()

        by_symbol: Dict[str, str] = {}
        for row in rows:
            sym = str(row.get("symbol", "")).upper()
            if sym and sym not in by_symbol:
                by_symbol[sym] = str(row["id"])
        _coin_list_cache = (now, by_symbol)

    return _coin_list_cache[1].get(upper)


def _generate_mock_prices(symbol: str, days: int) -> List[Dict[str, Any]]:
    """Synthetic price curve for demos and video testing."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(days, 1))

    seed = int(hashlib.sha256(symbol.upper().encode()).hexdigest()[:8], 16)
    base_price = 40 + (seed % 4000) / 10
    points: List[Dict[str, Any]] = []

    if days <= 1:
        step = timedelta(minutes=30)
        total_steps = 48
    elif days <= 7:
        step = timedelta(hours=2)
        total_steps = days * 12
    elif days <= 30:
        step = timedelta(hours=6)
        total_steps = days * 4
    else:
        step = timedelta(days=1)
        total_steps = days

    for index in range(total_steps + 1):
        ts = start + step * index
        if ts > now:
            break
        wave = math.sin(index / 7) * 0.06 + math.cos(index / 19) * 0.03
        trend = index / max(total_steps, 1) * 0.12
        noise = ((seed + index * 17) % 100) / 5000
        price = base_price * (1 + trend + wave + noise)
        points.append({"timestamp": ts, "price": round(price, 4)})

    return points


async def fetch_market_chart(symbol: str, days: int) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Return USD price history for a base symbol.

    Returns (points, is_mock). Points are dicts with timezone-aware UTC timestamps.
    """
    normalized = symbol.upper().strip()
    if not normalized:
        return [], False

    days = max(1, min(int(days), 365))
    cache_key = (normalized, days)
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < _cache_ttl():
        return cached[1], False

    if _is_mock_enabled():
        points = _generate_mock_prices(normalized, days)
        _cache[cache_key] = (now, points)
        return points, True

    coin_id = await _resolve_coin_id(normalized)
    if not coin_id:
        return [], False

    url = f"{_base_url()}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params, headers=_api_headers())
        response.raise_for_status()
        payload = response.json()

    points = []
    for ts_ms, price in payload.get("prices", []):
        points.append(
            {
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "price": float(price),
            }
        )

    _cache[cache_key] = (now, points)
    return points, False
