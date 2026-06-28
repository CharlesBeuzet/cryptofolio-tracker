"""Base connector interface for data providers."""
from abc import ABC, abstractmethod
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

