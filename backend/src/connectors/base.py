"""Base connector interface for data providers."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class BaseConnector(ABC):
    """Abstract base class for all data connectors."""

    def __init__(self, config: Dict):
        """
        Initialize connector with configuration.

        Args:
            config: Configuration dictionary with API keys, credentials, etc.
        """
        self.config = config
        self.name = self.__class__.__name__.lower().replace("connector", "")

    @abstractmethod
    async def fetch_balances(self) -> List[Dict]:
        """
        Fetch current balances from the data source.

        Returns:
            List of dictionaries with keys: symbol, quantity, exchange
        """
        pass

    @abstractmethod
    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Fetch order history from the data source.

        Args:
            symbol: Optional symbol to filter orders. If None, fetch all orders.

        Returns:
            List of dictionaries with keys: symbol, type (buy/sell), quantity, price, executed_at, exchange
        """
        pass

    @abstractmethod
    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch current prices for given symbols.

        Args:
            symbols: List of symbol strings (e.g., ['BTC/USDT', 'ETH/USDT'])

        Returns:
            Dictionary mapping symbol to price
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test if the connection to the data source is working.

        Returns:
            True if connection is successful, False otherwise
        """
        pass

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executed (filled) spot orders for one market pair (scheduler-safe sync HTTP).

        Args:
            market_pair: Unified ccxt symbol (e.g. BTC/USDT).
            since_ms: Earliest order timestamp in ms, or None for provider default (recent).
            limit: Maximum orders per API page (provider cap applies).
            paginate: When True, walk the full range (initial backfill).

        Returns:
            Normalized rows: external_order_id, symbol, type, quantity, price,
            executed_at (datetime), exchange.
        """
        return []

    def fetch_price_history_sync(
        self,
        market_pair: str,
        since_ms: int,
        *,
        days: int,
    ) -> List[Dict[str, Any]]:
        """
        Historical market prices for one spot pair (scheduler-safe sync HTTP).

        Candle resolution by range: 24h → 1h, 7d → 4h, 30d → 12h, 90d → 1d,
        longer (1Y / 2Y / 5Y) → 1w.
        Returns normalized rows: timestamp (datetime UTC), open, high, low, close,
        and price (alias of close for backward compatibility).
        """
        exchange = getattr(self, "exchange", None)
        if exchange is None:
            return []

        if days <= 1:
            timeframe = "1h"
        elif days <= 7:
            timeframe = "4h"
        elif days <= 30:
            timeframe = "12h"
        elif days <= 90:
            timeframe = "1d"
        else:
            timeframe = "1w"
        limit = 1000
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        since = since_ms
        raw_candles: List[List[float]] = []

        while since < now_ms:
            try:
                batch = exchange.fetch_ohlcv(
                    market_pair,
                    timeframe,
                    since=since,
                    limit=limit,
                )
            except Exception as exc:
                print(
                    f"Error fetching {timeframe} OHLCV for {market_pair} "
                    f"from {self.name}: {exc}"
                )
                break
            if not batch:
                break
            raw_candles.extend(batch)
            last_ts = int(batch[-1][0])
            if len(batch) < limit or last_ts >= now_ms:
                break
            since = last_ts + 1

        points: List[Dict[str, Any]] = []
        seen_ts: set[int] = set()
        for candle in raw_candles:
            if len(candle) < 5:
                continue
            ts_ms = int(candle[0])
            if ts_ms in seen_ts:
                continue
            seen_ts.add(ts_ms)
            try:
                open_ = float(candle[1])
                high = float(candle[2])
                low = float(candle[3])
                close = float(candle[4])
            except (TypeError, ValueError):
                continue
            points.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        ts_ms / 1000.0, tz=timezone.utc
                    ),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "price": close,
                }
            )
        return points

    def fetch_fiat_deposit_orders_sync(self, rows: int = 100) -> List[Dict[str, Any]]:
        """
        Recent fiat deposit (on-ramp) orders from this provider, if supported.

        Sync HTTP/API calls are acceptable here (used from the scheduler, not FastAPI handlers).

        Args:
            rows: Provider-specific maximum number of recent orders to return.

        Returns:
            Normalized rows with keys: external_order_id (str), currency (str), amount (float),
            optional fee (float), status (str), method (str), deposited_at (datetime).
            Providers without fiat rails return an empty list.
        """
        return []

