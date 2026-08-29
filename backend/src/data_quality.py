"""Reject failed or unusable connector payloads before they are persisted."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

# Amounts at or below this are treated as missing / dust, not a real quote.
VALUE_EPSILON = 1e-12


class ConnectorFetchError(Exception):
    """A connector request failed or returned data that must not be saved."""


def as_finite_float(value: Any) -> Optional[float]:
    """Parse a number, returning None for missing, NaN, or infinite values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def is_valid_price(value: Any) -> bool:
    number = as_finite_float(value)
    return number is not None and number > VALUE_EPSILON


def is_valid_quantity(value: Any) -> bool:
    number = as_finite_float(value)
    return number is not None and number > VALUE_EPSILON


def sanitize_prices(prices: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    """Keep only symbols with a strictly positive finite price."""
    if not prices:
        return {}
    cleaned: Dict[str, float] = {}
    for symbol, raw in prices.items():
        if not symbol:
            continue
        number = as_finite_float(raw)
        if number is None or number <= VALUE_EPSILON:
            continue
        cleaned[str(symbol)] = number
    return cleaned


def sanitize_balances(
    balances: Optional[Iterable[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Keep only balance rows with a symbol and a strictly positive quantity."""
    if not balances:
        return []
    cleaned: List[Dict[str, Any]] = []
    for row in balances:
        if not isinstance(row, Mapping):
            continue
        symbol = row.get("symbol")
        if not symbol or not str(symbol).strip():
            continue
        qty = as_finite_float(row.get("quantity"))
        if qty is None or qty <= VALUE_EPSILON:
            continue
        out = dict(row)
        out["symbol"] = str(symbol).strip()
        out["quantity"] = qty
        cleaned.append(out)
    return cleaned


def snapshot_skip_reason(
    total_value: Any,
    *,
    open_position_count: int,
    missing_price_count: int,
    last_value: Optional[float] = None,
) -> Optional[str]:
    """Return a skip reason when a portfolio snapshot would record junk data."""
    value = as_finite_float(total_value)
    if value is None:
        return "portfolio value is not a finite number"
    if value < 0:
        return "portfolio value is negative"
    if missing_price_count > 0 and value <= VALUE_EPSILON:
        return (
            f"{missing_price_count} open position(s) have no usable price; "
            "refusing to persist a zero snapshot"
        )
    last = as_finite_float(last_value) if last_value is not None else None
    if (
        open_position_count > 0
        and value <= VALUE_EPSILON
        and last is not None
        and last > VALUE_EPSILON
    ):
        return (
            "computed portfolio value is zero while open positions remain "
            "and the last snapshot was non-zero"
        )
    return None
