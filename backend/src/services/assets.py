"""Asset and position sync from exchange connectors."""
from datetime import datetime
from typing import Any, Dict, List, Set

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..models.database import Asset, Position
from .portfolio import PortfolioService


def _apply_stablecoin_usd_prices(prices: Dict[str, float], symbols) -> None:
    """Treat USD-pegged stables as ~1 USD when ticker fetch misses."""
    for sym in symbols:
        if sym in ("USDT", "USDC"):
            prices.setdefault(sym, 1.0)


class AssetsService:
    """Fetch holdings from connectors and sync assets/positions tables."""

    def __init__(self, db: Session):
        self.db = db
        self._portfolio = PortfolioService(db)

    async def _fetch_prices(self, connector: Any, symbols: List[str]) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        if not symbols:
            return prices
        try:
            prices = await connector.fetch_prices(list(symbols))
        except Exception as e:
            print(f"Error fetching prices from {connector.name}: {e}")
        _apply_stablecoin_usd_prices(prices, symbols)
        return prices

    def _sync_assets(self, balances: List[Dict], prices: Dict[str, float]) -> int:
        """Upsert Asset rows for symbols seen in balances. Returns count of rows touched."""
        symbols = {b["symbol"] for b in balances if b.get("quantity", 0) > 0}
        updated = 0
        for symbol in symbols:
            asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
            if not asset:
                asset = Asset(symbol=symbol, name=symbol)
                self.db.add(asset)
                updated += 1
            price = prices.get(symbol)
            if price:
                asset.current_price = price
                asset.last_updated = datetime.utcnow()
                updated += 1
        if updated:
            self.db.commit()
        return updated

    def _sync_positions(self, balances: List[Dict], exchange: str) -> Dict[str, int]:
        """Upsert open positions from balances; close stale ones for this exchange."""
        opened = 0
        closed = 0
        seen_symbols: Set[str] = set()

        for balance in balances:
            if balance.get("quantity", 0) <= 0:
                continue
            symbol = balance["symbol"]
            seen_symbols.add(symbol)
            self._portfolio.update_position_from_balance(
                symbol, balance["quantity"], exchange
            )
            opened += 1

        query = self.db.query(Position).filter(
            and_(Position.exchange == exchange, Position.status == "open")
        )
        if seen_symbols:
            query = query.filter(~Position.symbol.in_(seen_symbols))
        for position in query.all():
            position.status = "closed"
            position.quantity = 0
            position.last_updated = datetime.utcnow()
            closed += 1

        if closed:
            self.db.commit()

        return {"opened": opened, "closed": closed}

    async def sync_from_connector(self, connector: Any) -> Dict[str, int]:
        """Fetch balances and prices from one connector, then sync assets and positions."""
        exchange = connector.name
        print(f"Syncing assets from {exchange} ...")
        balances = await connector.fetch_balances()
        symbols = [b["symbol"] for b in balances if b.get("quantity", 0) > 0]
        prices = await self._fetch_prices(connector, symbols)
        assets_updated = self._sync_assets(balances, prices)
        position_counts = self._sync_positions(balances, exchange)
        return {
            "assets_updated": assets_updated,
            "positions_opened": position_counts["opened"],
            "positions_closed": position_counts["closed"],
        }
