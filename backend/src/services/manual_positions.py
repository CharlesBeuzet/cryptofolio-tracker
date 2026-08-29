"""CRUD and valuation helpers for user-declared (non-API) positions."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..models.database import Asset, Position, PositionValuation

SOURCE_SYNCED = "synced"
SOURCE_MANUAL = "manual"


def position_source(position: Position) -> str:
    return getattr(position, "source", None) or SOURCE_SYNCED


def is_manual_position(position: Position) -> bool:
    return position_source(position) == SOURCE_MANUAL


def sorted_valuations(position: Position) -> List[PositionValuation]:
    vals = list(getattr(position, "valuations", None) or [])
    return sorted(vals, key=lambda v: (v.recorded_at, v.id or 0))


def latest_valuation(position: Position) -> Optional[PositionValuation]:
    vals = sorted_valuations(position)
    return vals[-1] if vals else None


def earliest_valuation(position: Position) -> Optional[PositionValuation]:
    vals = sorted_valuations(position)
    return vals[0] if vals else None


def position_market_value(position: Position) -> float:
    """NAV contribution: last manual mark, or qty × market price for synced rows."""
    if is_manual_position(position):
        latest = latest_valuation(position)
        return float(latest.value_amount) if latest else 0.0
    price = position.asset.current_price if position.asset else None
    if price:
        return float(position.quantity or 0.0) * float(price)
    return 0.0


def manual_cost_basis(position: Position) -> float:
    first = earliest_valuation(position)
    return float(first.value_amount) if first else 0.0


def manual_avg_entry(position: Position) -> float:
    first = earliest_valuation(position)
    if not first:
        return 0.0
    qty = first.quantity if first.quantity is not None else position.quantity
    if qty and qty > 0:
        return float(first.value_amount) / float(qty)
    return 0.0


def manual_pnl(position: Position) -> tuple:
    """Return (unrealised_pnl, unrealised_pnl_percent) from first vs latest mark."""
    value = position_market_value(position)
    basis = manual_cost_basis(position)
    pnl = value - basis
    pct = (pnl / basis * 100.0) if basis else 0.0
    return pnl, pct


def position_cost_basis(position: Position) -> float:
    if is_manual_position(position):
        return manual_cost_basis(position)
    metrics = getattr(position, "metrics", None)
    if not metrics:
        return 0.0
    return float(metrics.avg_entry_price or 0.0) * float(metrics.order_derived_qty or 0.0)


class ManualPositionService:
    """Create and maintain manual positions and their valuation snapshots."""

    def __init__(self, db: Session):
        self.db = db

    def _load(self, position_id: int) -> Optional[Position]:
        return (
            self.db.query(Position)
            .options(
                joinedload(Position.asset),
                joinedload(Position.valuations),
                joinedload(Position.metrics),
                joinedload(Position.tag),
                joinedload(Position.orders),
            )
            .filter(Position.id == position_id)
            .first()
        )

    def _require_manual(self, position: Optional[Position], position_id: int) -> Position:
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if not is_manual_position(position):
            raise ValueError("Only manual positions can be edited this way")
        return position

    def _upsert_asset(self, symbol: str) -> Asset:
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            asset = Asset(symbol=symbol, name=symbol)
            self.db.add(asset)
            self.db.flush()
        return asset

    def _clean_symbol(self, symbol: str) -> str:
        cleaned = (symbol or "").strip().upper()
        if not cleaned:
            raise ValueError("Symbol is required")
        if len(cleaned) > 20:
            raise ValueError("Symbol must be 20 characters or fewer")
        return cleaned

    def _clean_venue(self, exchange: str) -> str:
        cleaned = (exchange or "").strip()
        if not cleaned:
            raise ValueError("Venue is required")
        if len(cleaned) > 50:
            raise ValueError("Venue must be 50 characters or fewer")
        return cleaned

    def _clean_display_name(self, display_name: Optional[str], required: bool = True) -> Optional[str]:
        cleaned = (display_name or "").strip() or None
        if required and not cleaned:
            raise ValueError("display_name is required for manual positions")
        if cleaned and len(cleaned) > 120:
            raise ValueError("Name must be 120 characters or fewer")
        return cleaned

    def _clean_url(self, external_url: Optional[str]) -> Optional[str]:
        cleaned = (external_url or "").strip() or None
        if cleaned and len(cleaned) > 500:
            raise ValueError("URL must be 500 characters or fewer")
        return cleaned

    def _assert_open_unique(self, symbol: str, exchange: str, exclude_id: Optional[int] = None) -> None:
        query = self.db.query(Position).filter(
            Position.symbol == symbol,
            Position.exchange == exchange,
            Position.status == "open",
            func.coalesce(Position.source, SOURCE_SYNCED) == SOURCE_MANUAL,
        )
        if exclude_id is not None:
            query = query.filter(Position.id != exclude_id)
        if query.first():
            raise ValueError(f"An open manual position already exists for {symbol} on {exchange}")

    def _apply_latest_state(self, position: Position) -> None:
        vals = (
            self.db.query(PositionValuation)
            .filter(PositionValuation.position_id == position.id)
            .order_by(PositionValuation.recorded_at.asc(), PositionValuation.id.asc())
            .all()
        )
        if not vals:
            position.quantity = 0.0
            return
        latest = vals[-1]
        if latest.quantity is not None:
            position.quantity = float(latest.quantity)
        else:
            with_qty = [v for v in reversed(vals) if v.quantity is not None]
            position.quantity = float(with_qty[0].quantity) if with_qty else 0.0
        position.first_bought_at = vals[0].recorded_at
        position.last_updated = datetime.utcnow()

    def create(
        self,
        display_name: str,
        symbol: str,
        exchange: str,
        external_url: Optional[str] = None,
        initial_value: Optional[float] = None,
        initial_quantity: Optional[float] = None,
        recorded_at: Optional[datetime] = None,
    ) -> Position:
        name = self._clean_display_name(display_name, required=True)
        symbol_key = self._clean_symbol(symbol)
        venue = self._clean_venue(exchange)
        url = self._clean_url(external_url)
        self._assert_open_unique(symbol_key, venue)

        if initial_value is not None and initial_value < 0:
            raise ValueError("Value must be zero or positive")
        if initial_quantity is not None and initial_quantity < 0:
            raise ValueError("Quantity must be zero or positive")

        asset = self._upsert_asset(symbol_key)
        stamp = recorded_at or datetime.utcnow()
        position = Position(
            asset_id=asset.id,
            symbol=symbol_key,
            quantity=float(initial_quantity) if initial_quantity is not None else 0.0,
            first_bought_at=stamp,
            exchange=venue,
            status="open",
            source=SOURCE_MANUAL,
            display_name=name,
            external_url=url,
        )
        self.db.add(position)
        self.db.flush()

        if initial_value is not None:
            self.db.add(
                PositionValuation(
                    position_id=position.id,
                    recorded_at=stamp,
                    value_amount=float(initial_value),
                    quantity=float(initial_quantity) if initial_quantity is not None else None,
                )
            )
            position.quantity = float(initial_quantity) if initial_quantity is not None else 0.0
            position.first_bought_at = stamp

        self.db.commit()
        loaded = self._load(position.id)
        return loaded or position

    def update(
        self,
        position_id: int,
        display_name: Optional[str] = None,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        external_url: Optional[str] = None,
    ) -> Position:
        position = self._require_manual(self._load(position_id), position_id)
        if display_name is not None:
            position.display_name = self._clean_display_name(display_name, required=True)
        if external_url is not None:
            position.external_url = self._clean_url(external_url)
        next_symbol = self._clean_symbol(symbol) if symbol is not None else position.symbol
        next_venue = self._clean_venue(exchange) if exchange is not None else (position.exchange or "")
        if symbol is not None or exchange is not None:
            self._assert_open_unique(next_symbol, next_venue, exclude_id=position.id)
            if symbol is not None:
                asset = self._upsert_asset(next_symbol)
                position.symbol = next_symbol
                position.asset_id = asset.id
            if exchange is not None:
                position.exchange = next_venue
        position.last_updated = datetime.utcnow()
        self.db.commit()
        loaded = self._load(position.id)
        return loaded or position

    def delete(self, position_id: int) -> bool:
        position = self._require_manual(
            self.db.query(Position).filter(Position.id == position_id).first(),
            position_id,
        )
        self.db.delete(position)
        self.db.commit()
        return True

    def add_valuation(
        self,
        position_id: int,
        value_amount: float,
        recorded_at: Optional[datetime] = None,
        quantity: Optional[float] = None,
    ) -> Position:
        position = self._require_manual(self._load(position_id), position_id)
        if value_amount < 0:
            raise ValueError("Value must be zero or positive")
        if quantity is not None and quantity < 0:
            raise ValueError("Quantity must be zero or positive")
        stamp = recorded_at or datetime.utcnow()
        self.db.add(
            PositionValuation(
                position_id=position.id,
                recorded_at=stamp,
                value_amount=float(value_amount),
                quantity=float(quantity) if quantity is not None else None,
            )
        )
        self.db.flush()
        self.db.refresh(position)
        self._apply_latest_state(position)
        self.db.commit()
        loaded = self._load(position.id)
        return loaded or position

    def delete_valuation(self, valuation_id: int) -> Position:
        valuation = (
            self.db.query(PositionValuation)
            .filter(PositionValuation.id == valuation_id)
            .first()
        )
        if not valuation:
            raise ValueError(f"Valuation {valuation_id} not found")
        position_id = valuation.position_id
        position = self._require_manual(self._load(position_id), position_id)
        self.db.delete(valuation)
        self.db.flush()
        self.db.refresh(position)
        self._apply_latest_state(position)
        self.db.commit()
        loaded = self._load(position.id)
        return loaded or position
