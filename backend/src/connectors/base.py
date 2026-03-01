"""Base connector interface for data providers."""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from datetime import datetime


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

