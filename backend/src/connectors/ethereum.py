"""Ethereum hot-wallet connector (RPC + public address)."""
from typing import Dict, List, Optional

from .base import BaseConnector


class EthereumConnector(BaseConnector):
    """Connector for an Ethereum hot wallet via JSON-RPC."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.hostname = (config.get("hostname") or "").strip()
        self.address = (config.get("address") or "").strip()

    async def fetch_balances(self) -> List[Dict]:
        """Wallet balance sync is not implemented yet."""
        return []

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Hot wallets have no exchange order history."""
        return []

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Price feeds are provided by exchange connectors."""
        return {}

    async def test_connection(self) -> bool:
        """Require both a public wallet address and an RPC hostname."""
        return bool(self.address and self.hostname)
