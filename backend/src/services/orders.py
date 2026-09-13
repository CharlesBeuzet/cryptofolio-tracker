"""Executed spot order sync from exchange connectors."""
from datetime import datetime, timedelta
from typing import Any, List, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..utils.data_quality import sanitize_row
from ..models.database import Order, Position
from .analyzer import PositionAnalyzerService

SYNC_OVERLAP_HOURS = 2
QUOTE_CURRENCIES = ("USDT", "USDC")


def _market_pairs(symbol: str) -> List[str]:
    """USDT and USDC market pairs for a base symbol (or the pair as-is if already qualified)."""
    if "/" in symbol:
        return [symbol]
    return [
        f"{symbol}/{quote}"
        for quote in QUOTE_CURRENCIES
        if symbol != quote
    ]


class OrderService:
    """Persist executed orders for open positions."""

    def __init__(self, db: Session):
        self.db = db

    def get_symbols_for_connector(self, connector: Any) -> List[str]:
        """Symbols with open positions on this exchange."""
        rows = (
            self.db.query(Position.symbol)
            .filter(
                Position.exchange == connector.name,
                Position.status == "open",
                Position.source == "synced",
            )
            .distinct()
            .all()
        )
        return sorted({r.symbol for r in rows if r.symbol})

    def _sync_params_for_symbol(self, exchange: str, symbol: str) -> Tuple[int, bool]:
        """Return (since_ms, paginate). Always limits to a recent window to avoid stale fills."""
        overlap = timedelta(hours=SYNC_OVERLAP_HOURS)
        last_at = (
            self.db.query(func.max(Order.executed_at))
            .filter(and_(Order.exchange == exchange, Order.symbol == symbol))
            .scalar()
        )
        if last_at is None:
            since = datetime.utcnow() - overlap
        else:
            since = last_at - overlap
        return int(since.timestamp() * 1000), False

    def _insert_orders(
        self, rows: List[dict], exchange: str, position: Position
    ) -> int:
        added = 0
        for row in rows:
            ext_id = row.get("external_order_id")
            if not ext_id:
                continue
            cleaned = sanitize_row(row)
            if cleaned is None:
                print(
                    f"Skipping invalid order {ext_id} on {exchange}: "
                    f"qty={row.get('quantity')} price={row.get('price')}"
                )
                continue
            row = cleaned
            exists = (
                self.db.query(Order)
                .filter(
                    Order.exchange == exchange,
                    Order.external_order_id == ext_id,
                )
                .first()
            )
            if exists:
                continue
            self.db.add(
                Order(
                    position_id=position.id,
                    symbol=row["symbol"],
                    type=row["type"],
                    quantity=row["quantity"],
                    price=row["price"],
                    executed_at=row["executed_at"],
                    exchange=exchange,
                    external_order_id=ext_id,
                )
            )
            added += 1
        return added

    def sync_orders_from_connector(self, connector: Any, symbol: str) -> int:
        """Fetch and persist new executed orders for one base symbol. Returns insert count."""
        exchange = connector.name
        since_ms, paginate = self._sync_params_for_symbol(exchange, symbol)

        position = (
            self.db.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.exchange == exchange,
                Position.status == "open",
                Position.source == "synced",
            )
            .first()
        )
        if not position:
            print(f"No open position for {symbol} on {exchange}; skipping order sync.")
            return 0

        total_added = 0
        for market_pair in _market_pairs(symbol):
            print(
                f"Syncing orders for {market_pair} from {exchange} "
                f"(since_ms={since_ms}, paginate={paginate}) ..."
            )
            raw = connector.fetch_orders_sync(
                market_pair, since_ms, paginate=paginate
            )
            total_added += self._insert_orders(raw, exchange, position)

        if total_added:
            self.db.commit()
            position = (
                self.db.query(Position)
                .options(joinedload(Position.asset))
                .filter(
                    Position.symbol == symbol,
                    Position.exchange == exchange,
                    Position.status == "open",
                Position.source == "synced",
                )
                .first()
            )
            if position:
                price = position.asset.current_price if position.asset else None
                PositionAnalyzerService(self.db).apply_new_orders(position.id, price)

        return total_added
