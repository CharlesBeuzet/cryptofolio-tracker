"""On-demand asset price history (not persisted).

Centralized exchanges use their connector's OHLCV feed. On-chain positions
(exchange ``solana`` or ``ethereum``) use Mobula with ``positions.token_address``.
That column is added by the wallet connector branch; this module only reads it.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..connectors.registry import get_connector_by_name
from ..utils.data_quality import ConnectorFetchError
from .mobula_client import MobulaClient

RESOLVED = "resolved"
NOT_FOUND = "not_found"

# Practical ceiling when the client requests Max (days <= 0). Weekly candles
# keep payload size reasonable across multi-year lookbacks.
MAX_PRICE_HISTORY_DAYS = 3650  # ~10 years

_cache: Dict[Tuple[str, str, int], Tuple[float, "MarketChartResult"]] = {}
_CACHE_TTL_SECONDS = 300

# positions.exchange values that are also Mobula chainId strings.
ONCHAIN_EXCHANGES = frozenset({"solana", "ethereum"})

TokenAddressLookup = Callable[[str, str], Optional[str]]


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


def clear_price_history_cache() -> None:
    """Drop the in-process chart cache. Tests use this between cases."""
    _cache.clear()


def lookup_onchain_token_address(
    symbol: str,
    exchange: str,
    *,
    database_path: Optional[Path] = None,
) -> Optional[str]:
    """Read positions.token_address for one synced on-chain position.

    Returns None when the database file or the column is absent. The wallet
    connector branch owns the migration and the first-sync write. Opens the
    database read-only and never creates or migrates it.
    """
    from ..models.database import DATABASE_PATH

    path = DATABASE_PATH if database_path is None else database_path
    if not path.is_file():
        return None

    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise ConnectorFetchError(
            f"Could not read token address: {exc}"
        ) from exc

    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(positions)")
        }
        if "token_address" not in columns:
            return None
        row = conn.execute(
            """
            SELECT token_address
            FROM positions
            WHERE upper(symbol) = ?
              AND lower(coalesce(exchange, '')) = ?
              AND source != 'manual'
              AND token_address IS NOT NULL
              AND trim(token_address) != ''
            ORDER BY CASE WHEN status = 'open' THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            (symbol.upper().strip(), exchange.lower().strip()),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ConnectorFetchError(
            f"Could not read token address: {exc}"
        ) from exc
    finally:
        conn.close()

    if row is None or row[0] is None:
        return None
    address = str(row[0]).strip()
    return address or None


class PriceHistoryService:
    """Fetch historical prices for a chart (in-memory cache only)."""

    def __init__(
        self,
        *,
        token_address_lookup: Optional[TokenAddressLookup] = None,
        mobula_client: Optional[MobulaClient] = None,
    ):
        self._token_address_lookup = (
            token_address_lookup or lookup_onchain_token_address
        )
        self._mobula_client = mobula_client

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

        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000
        )
        if exchange_name in ONCHAIN_EXCHANGES:
            result = self._fetch_onchain(
                normalized_symbol,
                exchange_name,
                since_ms,
                days=days,
            )
        else:
            result = self._fetch_cex(
                normalized_symbol,
                exchange_name,
                since_ms,
                days=days,
            )
        _cache[cache_key] = (now, result)
        return result

    def _fetch_onchain(
        self,
        symbol: str,
        exchange_name: str,
        since_ms: int,
        *,
        days: int,
    ) -> MarketChartResult:
        try:
            address = self._token_address_lookup(symbol, exchange_name)
        except ConnectorFetchError as exc:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"Price history request for {symbol} on {exchange_name} "
                    f"failed: {exc}"
                ),
            )

        if not address or not str(address).strip():
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"No on-chain token address stored for {symbol} on {exchange_name}."
                ),
            )

        try:
            points = self._mobula().fetch_ohlcv(
                str(address).strip(),
                exchange_name,
                since_ms,
                days=days,
            )
        except ConnectorFetchError as exc:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"Price history request for {symbol} on {exchange_name} "
                    f"failed: {exc}"
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

    def _fetch_cex(
        self,
        symbol: str,
        exchange_name: str,
        since_ms: int,
        *,
        days: int,
    ) -> MarketChartResult:
        connector = get_connector_by_name(exchange_name)
        if connector is None:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f'No configured connector found for exchange "{exchange_name}".'
                ),
            )

        market_pair = symbol if "/" in symbol else f"{symbol}/USDT"
        try:
            points = connector.fetch_price_history_sync(
                market_pair,
                since_ms,
                days=days,
            )
        except ConnectorFetchError as exc:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"Price history request for {market_pair} on "
                    f"{exchange_name} failed: {exc}"
                ),
            )

        if not points:
            return MarketChartResult(
                resolution_status=NOT_FOUND,
                ambiguity_message=(
                    f"No price history returned for {market_pair} on {exchange_name}."
                ),
            )
        return MarketChartResult(points=points, resolution_status=RESOLVED)

    def _mobula(self) -> MobulaClient:
        if self._mobula_client is None:
            self._mobula_client = MobulaClient()
        return self._mobula_client
