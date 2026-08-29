"""Reject failed or unusable connector payloads before they are persisted."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

# Amounts at or below this are treated as missing / dust, not a real quote.
VALUE_EPSILON = 1e-12
# Numeric columns that decide whether a connector row is worth keeping.
_QUALITY_FIELDS = ("quantity", "price")


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


def positive_finite(value: Any) -> Optional[float]:
    """Return value as float when it is finite and strictly positive, else None.

    Shared check for prices, quantities, and any other quote-like amount.
    """
    number = as_finite_float(value)
    if number is None or number <= VALUE_EPSILON:
        return None
    return number


def sanitize_row(row: Any) -> Optional[Dict[str, Any]]:
    """Keep a mapping row if it has a symbol and usable quantity/price columns.

    Present `quantity` and/or `price` keys must be strictly positive and finite.
    At least one of those columns must be present. Invalid or missing symbol,
    or a bad numeric column, drops the row.
    """
    if not isinstance(row, Mapping):
        return None
    symbol = row.get("symbol")
    if not symbol or not str(symbol).strip():
        return None
    out = dict(row)
    out["symbol"] = str(symbol).strip()
    seen_quality_field = False
    for key in _QUALITY_FIELDS:
        if key not in row:
            continue
        number = positive_finite(row.get(key))
        if number is None:
            return None
        out[key] = number
        seen_quality_field = True
    if not seen_quality_field:
        return None
    return out


def sanitize_rows(
    rows: Optional[Iterable[Any]],
) -> List[Dict[str, Any]]:
    """Apply sanitize_row to a collection; drop anything that fails the checks."""
    if not rows:
        return []
    cleaned_rows: List[Dict[str, Any]] = []
    for row in rows:
        cleaned = sanitize_row(row)
        if cleaned is not None:
            cleaned_rows.append(cleaned)
    return cleaned_rows


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
