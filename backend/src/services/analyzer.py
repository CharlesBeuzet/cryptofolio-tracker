"""Position analyzer: incremental order-derived metrics (average-cost method)."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from ..utils.data_quality import positive_finite
from ..models.database import Order, Position, PositionMetrics
from .metrics_helpers import QTY_EPSILON, has_qty_mismatch


class PositionAnalyzerService:
    """Compute and persist position metrics from order history and asset prices."""

    def __init__(self, db: Session):
        self.db = db

    def ensure_metrics(self, position_id: int) -> PositionMetrics:
        metrics = (
            self.db.query(PositionMetrics)
            .filter(PositionMetrics.position_id == position_id)
            .first()
        )
        if not metrics:
            metrics = PositionMetrics(position_id=position_id)
            self.db.add(metrics)
            self.db.flush()
        return metrics

    def _reset_metrics(self, metrics: PositionMetrics) -> None:
        metrics.avg_entry_price = 0.0
        metrics.avg_exit_price = None
        metrics.break_even_price = 0.0
        metrics.realised_pnl = 0.0
        metrics.realised_pnl_percent = 0.0
        metrics.unrealised_pnl = 0.0
        metrics.unrealised_pnl_percent = 0.0
        metrics.total_pnl = 0.0
        metrics.total_pnl_percent = 0.0
        metrics.holding_value = 0.0
        metrics.order_derived_qty = 0.0
        metrics.total_buy_qty = 0.0
        metrics.total_buy_cost = 0.0
        metrics.total_sell_qty = 0.0
        metrics.total_sell_proceeds = 0.0
        metrics.last_processed_order_id = None

    def _apply_buy(self, metrics: PositionMetrics, qty: float, price: float) -> None:
        trade_cost = qty * price
        metrics.total_buy_qty += qty
        metrics.total_buy_cost += trade_cost
        old_qty = metrics.order_derived_qty
        new_qty = old_qty + qty
        if new_qty > QTY_EPSILON:
            if old_qty > QTY_EPSILON:
                metrics.avg_entry_price = (
                    metrics.avg_entry_price * old_qty + trade_cost
                ) / new_qty
            else:
                metrics.avg_entry_price = price
        metrics.order_derived_qty = new_qty
        metrics.break_even_price = metrics.avg_entry_price

    def _apply_sell(self, metrics: PositionMetrics, qty: float, price: float) -> None:
        if qty > metrics.order_derived_qty + QTY_EPSILON:
            print(
                f"Warning: sell qty {qty} exceeds order_derived_qty "
                f"{metrics.order_derived_qty}; clamping."
            )
            qty = max(metrics.order_derived_qty, 0.0)
        proceeds = qty * price
        metrics.realised_pnl += (price - metrics.avg_entry_price) * qty
        metrics.total_sell_qty += qty
        metrics.total_sell_proceeds += proceeds
        metrics.order_derived_qty -= qty
        if metrics.order_derived_qty > QTY_EPSILON:
            metrics.break_even_price = metrics.avg_entry_price
        if metrics.total_sell_qty > QTY_EPSILON:
            metrics.avg_exit_price = metrics.total_sell_proceeds / metrics.total_sell_qty
        self._update_realised_percent(metrics)

    def _update_realised_percent(self, metrics: PositionMetrics) -> None:
        if metrics.total_buy_cost > QTY_EPSILON:
            metrics.realised_pnl_percent = (
                metrics.realised_pnl / metrics.total_buy_cost * 100
            )
        else:
            metrics.realised_pnl_percent = 0.0

    def _refresh_market(
        self, metrics: PositionMetrics, current_price: Optional[float]
    ) -> None:
        if metrics.order_derived_qty > QTY_EPSILON and positive_finite(current_price):
            metrics.holding_value = metrics.order_derived_qty * current_price
            remaining_cost = metrics.avg_entry_price * metrics.order_derived_qty
            metrics.unrealised_pnl = metrics.holding_value - remaining_cost
            if metrics.avg_entry_price > QTY_EPSILON:
                metrics.unrealised_pnl_percent = (
                    current_price / metrics.avg_entry_price - 1
                ) * 100
            else:
                metrics.unrealised_pnl_percent = 0.0
        elif metrics.order_derived_qty <= QTY_EPSILON:
            metrics.holding_value = 0.0
            metrics.unrealised_pnl = 0.0
            metrics.unrealised_pnl_percent = 0.0
        # else: keep last holding_value / unrealised PnL (quote missing or invalid)

        metrics.total_pnl = metrics.realised_pnl + metrics.unrealised_pnl
        if metrics.total_buy_cost > QTY_EPSILON:
            metrics.total_pnl_percent = (
                metrics.total_pnl / metrics.total_buy_cost * 100
            )
        else:
            metrics.total_pnl_percent = 0.0
        metrics.metrics_updated_at = datetime.utcnow()

    def _process_order(self, metrics: PositionMetrics, order: Order) -> None:
        if order.type == "buy":
            self._apply_buy(metrics, order.quantity, order.price)
        elif order.type == "sell":
            self._apply_sell(metrics, order.quantity, order.price)

    def _position_price(self, position_id: int) -> Optional[float]:
        position = (
            self.db.query(Position)
            .options(joinedload(Position.asset))
            .filter(Position.id == position_id)
            .first()
        )
        if position and position.asset:
            price = position.asset.current_price
            return positive_finite(price)
        return None

    def _log_qty_mismatch(self, position: Position, metrics: PositionMetrics) -> None:
        if has_qty_mismatch(metrics, position.quantity):
            print(
                f"Quantity mismatch for {position.symbol} on {position.exchange}: "
                f"balance={position.quantity}, orders={metrics.order_derived_qty}"
            )

    def apply_new_orders(
        self,
        position_id: int,
        current_price: Optional[float] = None,
    ) -> PositionMetrics:
        """Incrementally process orders newer than the watermark."""
        metrics = self.ensure_metrics(position_id)
        watermark = metrics.last_processed_order_id or 0
        new_orders: List[Order] = (
            self.db.query(Order)
            .filter(Order.position_id == position_id, Order.id > watermark)
            .order_by(Order.executed_at, Order.id)
            .all()
        )
        if current_price is None:
            current_price = self._position_price(position_id)

        for order in new_orders:
            self._process_order(metrics, order)
            metrics.last_processed_order_id = order.id

        self._refresh_market(metrics, current_price)

        position = self.db.query(Position).filter(Position.id == position_id).first()
        if position:
            self._log_qty_mismatch(position, metrics)

        self.db.commit()
        return metrics

    def refresh_market_metrics(
        self, position_id: int, current_price: Optional[float] = None
    ) -> PositionMetrics:
        """Recompute unrealised and total PnL after a price move."""
        metrics = self.ensure_metrics(position_id)
        if current_price is None:
            current_price = self._position_price(position_id)
        if positive_finite(current_price) is None and metrics.order_derived_qty > QTY_EPSILON:
            print(
                f"Warning: no usable current price for position {position_id}; "
                "keeping last unrealised PnL."
            )
        self._refresh_market(metrics, current_price)
        self.db.commit()
        return metrics

    def recompute_position(
        self, position_id: int, current_price: Optional[float] = None
    ) -> PositionMetrics:
        """Full rebuild from all orders (backfill / repair)."""
        metrics = self.ensure_metrics(position_id)
        self._reset_metrics(metrics)
        orders: List[Order] = (
            self.db.query(Order)
            .filter(Order.position_id == position_id)
            .order_by(Order.executed_at, Order.id)
            .all()
        )
        for order in orders:
            self._process_order(metrics, order)
            metrics.last_processed_order_id = order.id

        if current_price is None:
            current_price = self._position_price(position_id)
        self._refresh_market(metrics, current_price)

        position = self.db.query(Position).filter(Position.id == position_id).first()
        if position:
            self._log_qty_mismatch(position, metrics)

        self.db.commit()
        return metrics

    def backfill_if_missing(self) -> int:
        """Recompute positions that have orders but no metrics watermark yet."""
        count = 0
        positions = self.db.query(Position).all()
        for position in positions:
            metrics = (
                self.db.query(PositionMetrics)
                .filter(PositionMetrics.position_id == position.id)
                .first()
            )
            has_orders = (
                self.db.query(Order.id)
                .filter(Order.position_id == position.id)
                .first()
                is not None
            )
            needs_backfill = metrics is None or (
                has_orders and metrics.last_processed_order_id is None
            )
            if needs_backfill and has_orders:
                self.recompute_position(position.id)
                count += 1
            elif metrics is None:
                self.ensure_metrics(position.id)
                self.db.commit()
        return count

    def refresh_all_open_prices(self) -> int:
        """Refresh market metrics for every open position."""
        count = 0
        positions = (
            self.db.query(Position)
            .options(joinedload(Position.asset))
            .filter(Position.status == "open")
            .all()
        )
        for position in positions:
            price = position.asset.current_price if position.asset else None
            self.refresh_market_metrics(
                position.id, positive_finite(price)
            )
            count += 1
        return count
