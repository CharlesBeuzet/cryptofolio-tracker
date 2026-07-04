"""On-demand asset price history (CoinGecko, not persisted)."""
from ..clients.coingecko import MarketChartResult, fetch_market_chart


class PriceHistoryService:
    """Thin wrapper around the CoinGecko client."""

    async def fetch(self, symbol: str, days: int = 90) -> MarketChartResult:
        return await fetch_market_chart(symbol, days)
