"""CoinGecko market chart client with in-memory caching (no DB persistence)."""
from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config.loader import get_section

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"

_cache: Dict[Tuple[str, int], Tuple[float, "MarketChartResult"]] = {}
_coin_list_cache: Optional[Tuple[float, Dict[str, List[Dict[str, str]]]]] = None


@dataclass
class CoinCandidate:
    id: str
    name: str
    symbol: str


@dataclass
class MarketChartResult:
    points: List[Dict[str, Any]] = field(default_factory=list)
    is_mock: bool = False
    resolution_status: str = RESOLVED
    ambiguity_message: Optional[str] = None
    candidates: List[CoinCandidate] = field(default_factory=list)


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


def _config_symbol_overrides() -> Dict[str, str]:
    overrides = _coingecko_config().get("symbol_ids") or {}
    return {str(symbol).upper(): str(coin_id) for symbol, coin_id in overrides.items()}


async def _load_symbol_index() -> Dict[str, List[Dict[str, str]]]:
    """Build symbol -> all CoinGecko listings from /coins/list."""
    global _coin_list_cache
    now = time.monotonic()
    if _coin_list_cache is not None and now - _coin_list_cache[0] <= 86_400:
        return _coin_list_cache[1]

    url = f"{_base_url()}/coins/list"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=_api_headers())
        response.raise_for_status()
        rows = response.json()

    by_symbol: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        sym = str(row.get("symbol", "")).upper()
        coin_id = str(row.get("id", "")).strip()
        if not sym or not coin_id:
            continue
        by_symbol[sym].append(
            {
                "id": coin_id,
                "name": str(row.get("name", "")),
                "symbol": sym,
            }
        )

    index = dict(by_symbol)
    _coin_list_cache = (now, index)
    return index


async def _resolve_coin_id(symbol: str) -> Tuple[Optional[str], str, Optional[str], List[CoinCandidate]]:
    """
    Resolve a portfolio symbol to a CoinGecko coin id.

    Returns (coin_id, status, message, candidates).
    Config symbol_ids overrides always win and are treated as unambiguous.
    """
    upper = symbol.upper().strip()
    overrides = _config_symbol_overrides()
    if upper in overrides:
        return overrides[upper], RESOLVED, None, []

    index = await _load_symbol_index()
    matches = index.get(upper, [])
    candidates = [
        CoinCandidate(id=row["id"], name=row["name"], symbol=row["symbol"])
        for row in matches
    ]

    if not candidates:
        return (
            None,
            NOT_FOUND,
            f'No CoinGecko listing found for symbol "{upper}".',
            [],
        )

    if len(candidates) == 1:
        return candidates[0].id, RESOLVED, None, []

    preview = ", ".join(f'{c.name} ({c.id})' for c in candidates[:5])
    suffix = "…" if len(candidates) > 5 else ""
    message = (
        f'Symbol "{upper}" matches {len(candidates)} CoinGecko assets: {preview}{suffix}. '
        "Set coingecko.symbol_ids in settings/config.yaml to choose one."
    )
    return None, AMBIGUOUS, message, candidates


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


async def fetch_market_chart(symbol: str, days: int) -> MarketChartResult:
    """Return USD price history for a base symbol (not persisted)."""
    normalized = symbol.upper().strip()
    if not normalized:
        return MarketChartResult(
            resolution_status=NOT_FOUND,
            ambiguity_message="Symbol is required.",
        )

    days = max(1, min(int(days), 365))
    cache_key = (normalized, days)
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < _cache_ttl():
        return cached[1]

    if _is_mock_enabled():
        result = MarketChartResult(
            points=_generate_mock_prices(normalized, days),
            is_mock=True,
            resolution_status=RESOLVED,
        )
        _cache[cache_key] = (now, result)
        return result

    coin_id, status, message, candidates = await _resolve_coin_id(normalized)
    if status != RESOLVED or not coin_id:
        result = MarketChartResult(
            resolution_status=status,
            ambiguity_message=message,
            candidates=candidates,
        )
        _cache[cache_key] = (now, result)
        return result

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

    result = MarketChartResult(points=points, resolution_status=RESOLVED)
    _cache[cache_key] = (now, result)
    return result
