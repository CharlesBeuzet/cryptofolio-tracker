"""Manual buy orders for on-chain holdings that no swap explained."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from ..models.database import Order, Position
from ..utils.data_quality import positive_finite
from .analyzer import PositionAnalyzerService
from .portfolio import PortfolioService

MANUAL_ORDER_PREFIX = "manual:"
CEX_EXCHANGES = frozenset({"binance", "okx", "coinbase"})


def unpriced_quantity(position: Position) -> float:
    """Holding size not yet explained by buy orders minus sells."""
    derived = 0.0
    if position.metrics is not None and position.metrics.order_derived_qty is not None:
        derived = position.metrics.order_derived_qty
    return max(0.0, (position.quantity or 0.0) - derived)


def is_onchain_position(position: Position) -> bool:
    exchange = (position.exchange or "").strip().lower()
    return (
        position.source != "manual"
        and bool(position.token_address)
        and exchange not in CEX_EXCHANGES
    )


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class OnchainOrderService:
    """Add or remove user-entered buys, then rebuild position metrics immediately."""

    def __init__(self, db: Session):
        self.db = db

    def add_buy(
        self,
        position_id: int,
        quantity: float,
        price: float,
        executed_at: Optional[datetime] = None,
    ) -> Position:
        position = (
            self.db.query(Position)
            .options(joinedload(Position.metrics), joinedload(Position.asset))
            .filter(Position.id == position_id)
            .first()
        )
        if position is None:
            raise ValueError("Position not found.")
        if not is_onchain_position(position):
            raise ValueError("Manual buy orders are only available for on-chain positions.")
        qty = positive_finite(quantity)
        unit = positive_finite(price)
        if qty is None or unit is None:
            raise ValueError("Quantity and buy price must be positive numbers.")
        gap = unpriced_quantity(position)
        if qty - gap > 1e-8:
            raise ValueError(
                f"Quantity exceeds the unpriced holding ({gap:.8f})."
            )
        when = _naive_utc(executed_at or datetime.utcnow())
        self.db.add(
            Order(
                position_id=position.id,
                symbol=position.symbol,
                type="buy",
                quantity=qty,
                price=unit,
                executed_at=when,
                exchange=position.exchange,
                external_order_id=f"{MANUAL_ORDER_PREFIX}{uuid.uuid4()}",
            )
        )
        self.db.flush()
        spot = position.asset.current_price if position.asset else None
        PositionAnalyzerService(self.db).recompute_position(position.id, spot)
        reloaded = PortfolioService(self.db).get_position_by_id(position.id)
        if reloaded is None:
            raise ValueError("Position not found.")
        return reloaded

    def delete_manual(self, order_id: int) -> Position:
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order is None:
            raise ValueError("Order not found.")
        external_id = order.external_order_id or ""
        if not external_id.startswith(MANUAL_ORDER_PREFIX):
            raise ValueError("Only manually entered orders can be deleted.")
        position = (
            self.db.query(Position)
            .options(joinedload(Position.asset))
            .filter(Position.id == order.position_id)
            .first()
        )
        if position is None or not is_onchain_position(position):
            raise ValueError("Manual buy orders are only available for on-chain positions.")
        position_id = position.id
        spot = position.asset.current_price if position.asset else None
        self.db.delete(order)
        self.db.flush()
        PositionAnalyzerService(self.db).recompute_position(position_id, spot)
        reloaded = PortfolioService(self.db).get_position_by_id(position_id)
        if reloaded is None:
            raise ValueError("Position not found.")
        return reloaded
