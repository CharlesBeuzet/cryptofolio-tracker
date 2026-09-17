"""Executed spot order sync from exchange connectors."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple

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

    def _get_open_positions_by_symbol(self, exchange: str) -> Dict[str, Position]:
        """Return a dict mapping symbol to open synced position for the exchange."""
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

    def sync_all_orders_from_connector(self, connector: Any) -> int:
        """Fetch and persist executed orders for all open positions on this connector.

        Uses account-wide fetching if the connector supports it (e.g. OKX 7-day window),
        otherwise falls back to per-symbol fetching. Returns total insert count.
        """
        exchange = connector.name

        if not connector.supports_account_wide_order_fetch:
            symbols = self.get_symbols_for_connector(connector)
            total = 0
            for symbol in symbols:
                total += self.sync_orders_from_connector(connector, symbol)
            return total

        positions_by_symbol = self._get_open_positions_by_symbol(exchange)
        if not positions_by_symbol:
            print(f"No open positions on {exchange}; skipping account-wide order sync.")
            return 0

        print(
            f"Syncing orders for {len(positions_by_symbol)} position(s) "
            f"from {exchange} (account-wide 7-day window)..."
        )
        raw_orders = connector.fetch_all_recent_orders_sync()
        if not raw_orders:
            print(f"No recent orders returned from {exchange}.")
            return 0

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
