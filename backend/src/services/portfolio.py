"""Portfolio service for aggregating and calculating portfolio data."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from ..models.database import (
    Asset,
    Position,
    PortfolioSnapshot,
)


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
            )
            .filter(Position.status == "open")
        )

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value."""
        positions = self._open_positions_query().all()
        total_value = 0.0
        for position in positions:
            price = position.asset.current_price if position.asset else None
            if price:
                total_value += position.quantity * price
        return total_value

    def record_snapshot(self, min_interval_hours: float = 5.0) -> Optional[PortfolioSnapshot]:
        """Persist the current portfolio total value as a historical snapshot.

        Returns the new snapshot, or None if skipped because a recent one exists.
        """
        if min_interval_hours > 0:
            cutoff = datetime.utcnow() - timedelta(hours=min_interval_hours)
            recent = (
                self.db.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= cutoff)
                .first()
            )
            if recent:
                return None

        snapshot = PortfolioSnapshot(
            total_value=self.get_portfolio_value(),
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
            pnl = sum(
                (p.metrics.total_pnl if p.metrics else 0.0) for p in positions
            )
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
            )
            .filter(Position.id == position_id)
            .first()
        )

    def get_portfolio_history(
        self, days: int = 180
    ) -> List[Dict]:
        """Get portfolio value history for the last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        snapshots = (
            self.db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.timestamp >= cutoff_date)
            .order_by(PortfolioSnapshot.timestamp.asc())
            .all()
        )
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

    def update_position_from_balance(
        self, symbol: str, quantity: float, exchange: str
    ):
        """Update or create an open position from balance data."""
        position = (
            self.db.query(Position)
            .options(joinedload(Position.asset))
            .filter(and_(Position.symbol == symbol, Position.exchange == exchange))
            .first()
        )

        asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
        if not asset:
            asset = Asset(symbol=symbol, name=symbol)
            self.db.add(asset)
            self.db.flush()

        if position:
            position.quantity = quantity
            position.status = "open"
            position.last_updated = datetime.utcnow()
        else:
            position = Position(
                asset_id=asset.id,
                symbol=symbol,
                quantity=quantity,
                first_bought_at=datetime.utcnow(),
                exchange=exchange,
                status="open",
            )
            self.db.add(position)

        self.db.commit()
        return position
