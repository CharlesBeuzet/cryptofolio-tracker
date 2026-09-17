"""Executed spot order sync from exchange connectors."""
from collections import defaultdict
from typing import Any, Dict, List, Set

from sqlalchemy.orm import Session, joinedload

from ..models.database import Order, Position
from ..utils.data_quality import sanitize_row
from .analyzer import PositionAnalyzerService


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

    def _get_open_positions_by_symbol(self, exchange: str) -> Dict[str, Position]:
        """Map base symbol → open synced position for the exchange."""
        positions = (
            self.db.query(Position)
            .filter(
                Position.exchange == exchange,
                Position.status == "open",
                Position.source == "synced",
            )
            .all()
        )
        return {p.symbol: p for p in positions if p.symbol}

    def _is_cold_start(self, exchange: str) -> bool:
        """True when this exchange has no stored orders yet (use archive)."""
        exists = (
            self.db.query(Order.id).filter(Order.exchange == exchange).first()
        )
        return exists is None

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

    def _persist_fetched_orders(
        self,
        raw_orders: List[dict],
        exchange: str,
        positions_by_symbol: Dict[str, Position],
    ) -> int:
        orders_by_symbol: Dict[str, List[dict]] = defaultdict(list)
        for row in raw_orders:
            symbol = row.get("symbol")
            if symbol:
                orders_by_symbol[symbol].append(row)

        total_added = 0
        updated_position_ids: Set[int] = set()

        for symbol, orders in orders_by_symbol.items():
            position = positions_by_symbol.get(symbol)
            if not position:
                continue
            added = self._insert_orders(orders, exchange, position)
            if added:
                total_added += added
                updated_position_ids.add(position.id)

        if total_added:
            self.db.commit()
            analyzer = PositionAnalyzerService(self.db)
            for pos_id in updated_position_ids:
                position = (
                    self.db.query(Position)
                    .options(joinedload(Position.asset))
                    .filter(Position.id == pos_id)
                    .first()
                )
                if position:
                    price = position.asset.current_price if position.asset else None
                    analyzer.apply_new_orders(position.id, price)

        return total_added

    def sync_all_orders_from_connector(self, connector: Any) -> int:
        """Fetch and persist executed orders for all open positions on this connector.

        Same call path for every connector:
        - cold start (no orders stored for the exchange) → fetch_archived_orders_sync
        - otherwise → fetch_recent_orders_sync (last 7 days)

        Each connector implements those methods; the service never branches on
        connector type. Returns total insert count.
        """
        exchange = connector.name
        positions_by_symbol = self._get_open_positions_by_symbol(exchange)
        if not positions_by_symbol:
            print(f"No open positions on {exchange}; skipping order sync.")
            return 0

        symbols = sorted(positions_by_symbol.keys())
        if self._is_cold_start(exchange):
            print(
                f"Cold start for {exchange}: fetching archived orders "
                f"for {len(symbols)} position(s)..."
            )
            raw_orders = connector.fetch_archived_orders_sync(symbols)
        else:
            print(
                f"Syncing recent orders from {exchange} "
                f"for {len(symbols)} position(s)..."
            )
            raw_orders = connector.fetch_recent_orders_sync(symbols)

        if not raw_orders:
            print(f"No orders returned from {exchange}.")
            return 0

        return self._persist_fetched_orders(
            raw_orders, exchange, positions_by_symbol
        )
