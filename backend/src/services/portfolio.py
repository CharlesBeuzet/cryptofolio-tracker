"""Portfolio service for aggregating and calculating portfolio data."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, case, func

from ..utils.data_quality import positive_finite, snapshot_skip_reason
from ..models.database import (
    Asset,
    Position,
    PortfolioSnapshot,
)
from .manual_positions import is_manual_position, manual_pnl, position_market_value


def token_identity(token_address: str) -> str:
    """EVM addresses compare case-insensitively. Solana mints do not."""
    text = token_address.strip()
    if text.lower().startswith("0x"):
        return text.lower()
    return text


def _token_clause(column, token_address: str):
    identity = token_identity(token_address)
    if identity.startswith("0x"):
        return func.lower(column) == identity
    return column == identity


class PortfolioService:
    """Service for portfolio calculations and aggregations."""

    def __init__(self, db: Session):
        self.db = db

    def _open_positions_query(self):
        return (
            self.db.query(Position)
            .options(
                joinedload(Position.asset),
                joinedload(Position.orders),
                joinedload(Position.metrics),
                joinedload(Position.tag),
                joinedload(Position.valuations),
            )
            .filter(Position.status == "open")
        )

    def get_portfolio_valuation(self) -> Tuple[float, int, int]:
        """Return (total_value, open_position_count, missing_price_count)."""
        positions = self._open_positions_query().all()
        total_value = 0.0
        missing_price_count = 0
        for position in positions:
            if is_manual_position(position):
                parsed = positive_finite(position_market_value(position))
                if parsed is None:
                    missing_price_count += 1
                    continue
                total_value += parsed
                continue

            parsed_qty = positive_finite(position.quantity)
            if parsed_qty is None:
                continue
            price = position.asset.current_price if position.asset else None
            parsed_price = positive_finite(price)
            if parsed_price is None:
                missing_price_count += 1
                continue
            total_value += parsed_qty * parsed_price
        return total_value, len(positions), missing_price_count

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value from positions with a usable price."""
        total_value, _, _ = self.get_portfolio_valuation()
        return total_value

    def record_snapshot(self, min_interval_hours: float = 5.0) -> Optional[PortfolioSnapshot]:
        """Persist the current portfolio total value as a historical snapshot.

        Returns the new snapshot, or None if skipped because a recent one exists
        or because the computed value fails the quality gate (e.g. a zero
        total while holdings have no usable prices).
        """
        if min_interval_hours > 0:
            cutoff = datetime.utcnow() - timedelta(hours=min_interval_hours)
            recent = (
                self.db.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= cutoff)
                .first()
            )
            if recent:
                print("Portfolio snapshot skipped (recent snapshot exists).")
                return None

        total_value, open_count, missing_prices = self.get_portfolio_valuation()
        last = (
            self.db.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .first()
        )
        skip = snapshot_skip_reason(
            total_value,
            open_position_count=open_count,
            missing_price_count=missing_prices,
            last_value=last.total_value if last else None,
        )
        if skip:
            print(f"Portfolio snapshot skipped ({skip}).")
            return None

        snapshot = PortfolioSnapshot(
            total_value=total_value,
            timestamp=datetime.utcnow(),
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def get_todays_pnl(self) -> Dict[str, float]:
        """Calculate today's P&L."""
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())

        current_value = self.get_portfolio_value()

        snapshot = (
            self.db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.timestamp >= today_start)
            .order_by(PortfolioSnapshot.timestamp.asc())
            .first()
        )

        if snapshot:
            pnl = current_value - snapshot.total_value
            pnl_percent = (pnl / snapshot.total_value * 100) if snapshot.total_value > 0 else 0
        else:
            positions = self._open_positions_query().all()
            pnl = 0.0
            for position in positions:
                if is_manual_position(position):
                    pnl += manual_pnl(position)[0]
                elif position.metrics:
                    pnl += position.metrics.total_pnl
            pnl_percent = (
                (pnl / (current_value - pnl) * 100) if (current_value - pnl) > 0 else 0
            )

        return {"pnl": pnl, "pnl_percent": pnl_percent, "value": current_value}

    def get_positions(self, limit: Optional[int] = None) -> List[Position]:
        """Get all open positions, optionally limited."""
        query = self._open_positions_query()
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_position_by_id(self, position_id: int) -> Optional[Position]:
        """Get a specific position by ID."""
        return (
            self.db.query(Position)
            .options(
                joinedload(Position.asset),
                joinedload(Position.orders),
                joinedload(Position.metrics),
                joinedload(Position.tag),
                joinedload(Position.valuations),
            )
            .filter(Position.id == position_id)
            .first()
        )

    def get_portfolio_history(
        self, days: int = 180
    ) -> List[Dict]:
        """Get portfolio value history for the last N days.

        Pass days <= 0 for Max: return all stored snapshots with no cutoff.
        """
        query = self.db.query(PortfolioSnapshot)
        if days > 0:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(PortfolioSnapshot.timestamp >= cutoff_date)
        snapshots = query.order_by(PortfolioSnapshot.timestamp.asc()).all()
        return [
            {"timestamp": s.timestamp, "value": s.total_value} for s in snapshots
        ]

    def get_daily_pnl_history(self, days: int = 30) -> List[Dict]:
        """Get daily P&L history."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        snapshots = (
            self.db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.timestamp >= cutoff_date)
            .order_by(PortfolioSnapshot.timestamp.asc())
            .all()
        )

        daily_pnl = []
        for i in range(1, len(snapshots)):
            pnl = snapshots[i].total_value - snapshots[i - 1].total_value
            pnl_percent = (
                (pnl / snapshots[i - 1].total_value * 100)
                if snapshots[i - 1].total_value > 0
                else 0
            )
            daily_pnl.append(
                {
                    "date": snapshots[i].timestamp.date(),
                    "pnl": pnl,
                    "pnl_percent": pnl_percent,
                }
            )

        return daily_pnl

    def _apply_spot(self, asset: Optional[Asset], spot_price: Optional[float]) -> None:
        price = positive_finite(spot_price)
        if asset is None or price is None:
            return
        asset.current_price = price
        asset.last_updated = datetime.utcnow()

    def update_position_from_balance(
        self,
        symbol: str,
        quantity: float,
        exchange: str,
        token_address: Optional[str] = None,
        spot_price: Optional[float] = None,
    ):
        """Update or create an open position from balance data.

        On-chain rows match on (exchange, token_address) so a ticker suffix
        assigned on an earlier sync stays put. CEX rows still match on
        (symbol, exchange) and keep a null token address.
        """
        query = (
            self.db.query(Position)
            .options(joinedload(Position.asset))
            .filter(
                Position.exchange == exchange,
                Position.source != "manual",
            )
        )
        if token_address:
            query = query.filter(_token_clause(Position.token_address, token_address))
        else:
            query = query.filter(
                Position.symbol == symbol,
                Position.token_address.is_(None),
            )
        position = query.order_by(
            case((Position.status == "open", 0), else_=1),
            Position.id.desc(),
        ).first()

        if position:
            position.quantity = quantity
            position.status = "open"
            position.last_updated = datetime.utcnow()
            self._apply_spot(position.asset, spot_price)
        else:
            asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
            if not asset:
                asset = Asset(symbol=symbol, name=symbol)
                self.db.add(asset)
                self.db.flush()
            self._apply_spot(asset, spot_price)
            position = Position(
                asset_id=asset.id,
                symbol=symbol,
                quantity=quantity,
                first_bought_at=datetime.utcnow(),
                exchange=exchange,
                status="open",
                source="synced",
                token_address=token_address,
            )
            self.db.add(position)

        self.db.commit()
        return position

    def ensure_token_position(
        self,
        symbol: str,
        exchange: str,
        token_address: str,
        *,
        executed_at: datetime,
        name: Optional[str] = None,
    ) -> Position:
        """Find the on-chain position for a contract, or open a closed shell for an order.

        A zero-quantity closed row keeps the order without showing a holding the
        balance sync has not confirmed. The next balance sync reopens it.
        """
        position = (
            self.db.query(Position)
            .filter(
                Position.exchange == exchange,
                Position.source != "manual",
                _token_clause(Position.token_address, token_address),
            )
            .order_by(
                case((Position.status == "open", 0), else_=1),
                Position.id.desc(),
            )
            .first()
        )
        if position:
            return position

        symbol = self._free_chain_symbol(symbol, exchange, token_address)
        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            asset = Asset(symbol=symbol, name=name or symbol)
            self.db.add(asset)
            self.db.flush()
        position = Position(
            asset_id=asset.id,
            symbol=symbol,
            quantity=0,
            first_bought_at=executed_at,
            exchange=exchange,
            status="closed",
            source="synced",
            token_address=token_address,
        )
        self.db.add(position)
        self.db.flush()
        return position

    def _free_chain_symbol(self, symbol: str, exchange: str, token_address: str) -> str:
        """Avoid colliding with another contract that already uses this ticker."""
        candidate = (symbol or "TOKEN")[:20]
        taken = (
            self.db.query(Position)
            .filter(
                Position.exchange == exchange,
                Position.symbol == candidate,
                Position.source != "manual",
            )
            .all()
        )
        if not taken:
            return candidate
        suffix = token_address[-4:].upper()
        room = max(1, 19 - len(suffix))
        alt = f"{candidate[:room]}-{suffix}"[:20]
        return alt
