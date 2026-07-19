"""On-demand asset price history from exchange connectors (not persisted)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..connectors.registry import get_connector_by_name

RESOLVED = "resolved"
NOT_FOUND = "not_found"

# Practical ceiling when the client requests Max (days <= 0). Weekly candles
# keep payload size reasonable across multi-year lookbacks.
MAX_PRICE_HISTORY_DAYS = 3650  # ~10 years

_cache: Dict[Tuple[str, str, int], Tuple[float, "MarketChartResult"]] = {}
_CACHE_TTL_SECONDS = 300


@dataclass
class CoinCandidate:
    """Kept for GraphQL compatibility; unused with exchange-sourced history."""

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


class PriceHistoryService:
    """Fetch historical prices for a symbol/USDT pair from the position's exchange."""

    async def fetch(
        self,
        symbol: str,
        days: int,
        exchange: Optional[str] = None,
    ) -> MarketChartResult:
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message="Symbol is required.",
            )

        if not exchange or not exchange.strip():
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message="Exchange is required to load price history.",
            )

        exchange_name = exchange.strip().lower()
        requested_days = int(days)
        # days <= 0 means Max (all available / exchange-capped lookback).
        days = (
            MAX_PRICE_HISTORY_DAYS
            if requested_days <= 0
            else max(1, requested_days)
        )
        cache_key = (normalized_symbol, exchange_name, days)
        now = time.monotonic()
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        connector = get_connector_by_name(exchange_name)
        if connector is None:
            result = MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f'No configured connector found for exchange "{exchange_name}".'
                ),
            )
            _cache[cache_key] = (now, result)
            return result

        market_pair = (
            normalized_symbol
            if "/" in normalized_symbol
            else f"{normalized_symbol}/USDT"
        )
        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000
        )

        points = connector.fetch_price_history_sync(
            market_pair,
            since_ms,
            days=days,
        )

        if not points:
            result = MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f'No price history returned for {market_pair} on {exchange_name}.'
                ),
            )
            _cache[cache_key] = (now, result)
            return result

        result = MarketChartResult(points=points, resolution_status=RESOLVED)
        _cache[cache_key] = (now, result)
        return result
