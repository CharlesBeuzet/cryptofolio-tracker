"""On-demand asset price history from exchange connectors (not persisted)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..config.loader import get_section
from ..connectors.registry import get_connector_by_name
from ..models.database import Position
from ..utils.data_quality import ConnectorFetchError
from .mobula_client import MobulaClient, chain_slug, chart_address, ohlcv_window, parse_ohlcv

RESOLVED = "resolved"
NOT_FOUND = "not_found"

# Practical ceiling when the client requests Max (days <= 0). Weekly candles
# keep payload size reasonable across multi-year lookbacks.
MAX_PRICE_HISTORY_DAYS = 3650  # ~10 years

_cache: Dict[Tuple[str, str, int, str], Tuple[float, "MarketChartResult"]] = {}
_CACHE_TTL_SECONDS = 300
_ONCHAIN_CACHE_TTL_SECONDS = 3600


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

    def __init__(
        self,
        client: Optional[MobulaClient] = None,
        chain_slugs: Optional[List[str]] = None,
    ):
        self._client = client
        self._chain_slugs = chain_slugs

    def _onchain_slugs(self) -> set[str]:
        if self._chain_slugs is not None:
            slugs = {chain_slug(item) for item in self._chain_slugs}
        else:
            section = get_section("mobula")
            slugs = {chain_slug(item) for item in (section.get("blockchains") or [])}
        slugs.discard(None)
        return slugs

    async def fetch(
        self,
        symbol: str,
        days: int,
        exchange: Optional[str] = None,
        token_address: Optional[str] = None,
        db: Any = None,
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
        token_key = (token_address or "").strip()
        cache_token = token_key.lower() if token_key.lower().startswith("0x") else token_key
        cache_key = (normalized_symbol, exchange_name, days, cache_token)
        now = time.monotonic()
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        if exchange_name in self._onchain_slugs():
            result = self._fetch_mobula(
                normalized_symbol,
                exchange_name,
                days,
                token_address,
                db,
            )
            ttl = (
                _ONCHAIN_CACHE_TTL_SECONDS
                if result.resolution_status == RESOLVED
                else _CACHE_TTL_SECONDS
            )
            _cache[cache_key] = (now + ttl, result)
            return result

        connector = get_connector_by_name(exchange_name)
        if connector is None:
            result = MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f'No configured connector found for exchange "{exchange_name}".'
                ),
            )
            _cache[cache_key] = (now + _CACHE_TTL_SECONDS, result)
            return result

        market_pair = (
            normalized_symbol
            if "/" in normalized_symbol
            else f"{normalized_symbol}/USDT"
        )
        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000
        )

        try:
            points = connector.fetch_price_history_sync(
                market_pair,
                since_ms,
                days=days,
            )
        except ConnectorFetchError as exc:
            result = MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"Price history request for {market_pair} on "
                    f"{exchange_name} failed: {exc}"
                ),
            )
            _cache[cache_key] = (now + _CACHE_TTL_SECONDS, result)
            return result

        if not points:
            result = MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f'No price history returned for {market_pair} on {exchange_name}.'
                ),
            )
            _cache[cache_key] = (now + _CACHE_TTL_SECONDS, result)
            return result

        result = MarketChartResult(points=points, resolution_status=RESOLVED)
        _cache[cache_key] = (now + _CACHE_TTL_SECONDS, result)
        return result

    def _fetch_mobula(
        self,
        symbol: str,
        exchange_name: str,
        days: int,
        token_address: Optional[str],
        db: Any,
    ) -> MarketChartResult:
        address = (token_address or "").strip()
        if not address:
            address, error = self._lookup_token(db, symbol, exchange_name)
            if error:
                return MarketChartResult(
                    resolution_status=NOT_FOUND,
                    ambiguity_message=error,
                )
        chart_token = chart_address(exchange_name, address)
        period, amount = ohlcv_window(days)
        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000
        )
        try:
            payload = self._mobula_client().ohlcv(
                chart_token,
                exchange_name,
                period=period,
                amount=amount,
                from_ms=since_ms,
            )
            points = parse_ohlcv(payload)
        except ConnectorFetchError as exc:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"Price history request for {symbol} on {exchange_name} failed: {exc}"
                ),
            )
        if not points:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"No price history returned for {symbol} on {exchange_name}."
                ),
            )
        return MarketChartResult(points=points, resolution_status=RESOLVED)

    def _lookup_token(self, db: Any, symbol: str, exchange_name: str) -> Tuple[str, Optional[str]]:
        if db is None:
            return "", "Token address is required to load this chart."
        rows = (
            db.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.exchange == exchange_name,
                Position.token_address.isnot(None),
                Position.status == "open",
                Position.source != "manual",
            )
            .all()
        )
        if len(rows) == 1:
            return rows[0].token_address, None
        if len(rows) > 1:
            return "", (
                f"Several contracts share {symbol} on {exchange_name}. "
                "Open one position to load its chart."
            )
        return "", f"No token address stored for {symbol} on {exchange_name}."

    def _mobula_client(self) -> MobulaClient:
        if self._client is not None:
            return self._client
        section = get_section("mobula")
        api_key = str(section.get("api_key") or "").strip()
        if not api_key:
            raise ConnectorFetchError("Mobula API key is missing")
        self._client = MobulaClient(api_key)
        return self._client
