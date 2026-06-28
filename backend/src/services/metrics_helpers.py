"""Derived position metric helpers (not persisted)."""
from ..models.database import PositionMetrics

QTY_EPSILON = 1e-10


def cost_basis(metrics: PositionMetrics) -> float:
    """Remaining book cost of unsold units (USD)."""
    return metrics.avg_entry_price * metrics.order_derived_qty


def cash_in_trade(metrics: PositionMetrics) -> float:
    """Net capital deployed minus proceeds withdrawn (USD). Positive after a loss when fully exited."""
    return metrics.total_buy_cost - metrics.total_sell_proceeds


def has_qty_mismatch(metrics: PositionMetrics, balance_qty: float) -> bool:
    """True when order-derived quantity diverges from exchange-reported balance."""
    return abs(metrics.order_derived_qty - balance_qty) > QTY_EPSILON
