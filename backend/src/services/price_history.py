"""On-demand asset price history (CoinGecko, not persisted)."""
from typing import Any, Dict, List, Tuple

from ..clients.coingecko import fetch_market_chart


class PriceHistoryService:
    """Thin wrapper around the CoinGecko client."""

    async def fetch(self, symbol: str, days: int = 90) -> Tuple[List[Dict[str, Any]], bool]:
        return await fetch_market_chart(symbol, days)
