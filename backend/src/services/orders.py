"""Executed spot order sync from exchange connectors."""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..utils.data_quality import sanitize_row
from ..models.database import MobulaActivityCursor, Order, Position
from .analyzer import PositionAnalyzerService
from .portfolio import PortfolioService

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

    def sync_wallet_activity(self, connector: Any) -> int:
        """Page Mobula wallet activity and store swap legs as orders.

        The first run walks history backward, at most 20 pages per wallet.
        Later runs pull one page of newer transactions, then continue the
        backfill if it has not finished. Each page is committed before the
        next request so a retry does not repurchase the same history.
        """
        if not getattr(connector, "syncs_wallet_activity", False):
            return 0
        added = 0
        for wallet in connector.wallets():
            cursor = self.db.get(MobulaActivityCursor, wallet)
            if cursor is None:
                cursor = MobulaActivityCursor(wallet=wallet, backfill_done=False)
                self.db.add(cursor)
                self.db.flush()
            already_scanned = cursor.newest_tx_ms is not None or bool(cursor.backfill_done)
            if already_scanned:
                if cursor.newest_tx_ms is not None:
                    page = connector.fetch_activity_page(
                        wallet, from_ms=int(cursor.newest_tx_ms)
                    )
                else:
                    page = connector.fetch_activity_page(wallet)
                added += self._persist_chain_orders(page.get("orders") or [])
                self._note_activity_cursor(cursor, page, finished_backfill=False)
                self.db.commit()
            if cursor.backfill_done:
                continue
            to_ms = (int(cursor.oldest_tx_ms) - 1) if cursor.oldest_tx_ms else None
            for _ in range(20):
                page = connector.fetch_activity_page(wallet, to_ms=to_ms)
                added += self._persist_chain_orders(page.get("orders") or [])
                page_size = int(page.get("page_size") or 100)
                finished = int(page.get("count") or 0) < page_size
                self._note_activity_cursor(cursor, page, finished_backfill=finished)
                self.db.commit()
                if cursor.backfill_done or page.get("oldest_tx_ms") is None:
                    break
                to_ms = int(page["oldest_tx_ms"]) - 1
        return added

    def _note_activity_cursor(
        self,
        cursor: MobulaActivityCursor,
        page: Dict[str, Any],
        *,
        finished_backfill: bool,
    ) -> None:
        oldest = page.get("oldest_tx_ms")
        newest = page.get("newest_tx_ms")
        if oldest is not None:
            cursor.oldest_tx_ms = (
                int(oldest)
                if cursor.oldest_tx_ms is None
                else min(int(cursor.oldest_tx_ms), int(oldest))
            )
        if newest is not None:
            cursor.newest_tx_ms = (
                int(newest)
                if cursor.newest_tx_ms is None
                else max(int(cursor.newest_tx_ms), int(newest))
            )
        if finished_backfill:
            cursor.backfill_done = True

    def _persist_chain_orders(self, rows: List[dict]) -> int:
        """Insert swap legs and rebuild metrics in executed_at order."""
        added = 0
        touched: Set[int] = set()
        portfolio = PortfolioService(self.db)
        for row in rows:
            ext_id = row.get("external_order_id")
            exchange = row.get("exchange")
            token = row.get("token_address")
            if not ext_id or not exchange or not token:
                continue
            cleaned = sanitize_row(row)
            if cleaned is None:
                continue
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
            position = portfolio.ensure_token_position(
                cleaned["symbol"],
                exchange,
                token,
                executed_at=cleaned["executed_at"],
                name=row.get("name"),
            )
            self.db.add(
                Order(
                    position_id=position.id,
                    symbol=position.symbol,
                    type=cleaned["type"],
                    quantity=cleaned["quantity"],
                    price=cleaned["price"],
                    executed_at=cleaned["executed_at"],
                    exchange=exchange,
                    external_order_id=ext_id,
                )
            )
            touched.add(position.id)
            added += 1
        if not added:
            return 0
        self.db.commit()
        analyzer = PositionAnalyzerService(self.db)
        for position_id in touched:
            position = (
                self.db.query(Position)
                .options(joinedload(Position.asset))
                .filter(Position.id == position_id)
                .first()
            )
            price = position.asset.current_price if position and position.asset else None
            analyzer.recompute_position(position_id, price)
        return added
