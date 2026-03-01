"""Portfolio service for aggregating and calculating portfolio data."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ..models.database import (
    Asset,
    Position,
    Order,
    PortfolioSnapshot,
    SessionLocal,
)


class PortfolioService:
    """Service for portfolio calculations and aggregations."""

    def __init__(self, db: Session):
        self.db = db

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value."""
        positions = self.db.query(Position).filter(Position.quantity > 0).all()
        total_value = 0.0
        for position in positions:
            if position.current_price:
                total_value += position.quantity * position.current_price
        return total_value

    def get_todays_pnl(self) -> Dict[str, float]:
        """Calculate today's P&L."""
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())

        # Get portfolio value now
        current_value = self.get_portfolio_value()

        # Get portfolio value at start of today
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
            # If no snapshot for today, calculate from positions
            positions = self.db.query(Position).filter(Position.quantity > 0).all()
            pnl = sum(p.pnl or 0 for p in positions)
            pnl_percent = (
                (pnl / (current_value - pnl) * 100) if (current_value - pnl) > 0 else 0
            )

        return {"pnl": pnl, "pnl_percent": pnl_percent, "value": current_value}

    def get_positions(self, limit: Optional[int] = None) -> List[Position]:
        """Get all positions, optionally limited."""
        query = self.db.query(Position).filter(Position.quantity > 0)
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_position_by_id(self, position_id: int) -> Optional[Position]:
        """Get a specific position by ID."""
        return self.db.query(Position).filter(Position.id == position_id).first()

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
        self, symbol: str, quantity: float, exchange: str, current_price: Optional[float] = None
    ):
        """Update or create position from balance data."""
        # Find existing position for this symbol and exchange
        position = (
            self.db.query(Position)
            .filter(and_(Position.symbol == symbol, Position.exchange == exchange))
            .first()
        )

        if position:
            # Update existing position
            position.quantity = quantity
            if current_price:
                position.current_price = current_price
                position.pnl = (current_price - position.avg_entry_price) * quantity
                position.pnl_percent = (
                    ((current_price - position.avg_entry_price) / position.avg_entry_price * 100)
                    if position.avg_entry_price > 0
                    else 0
                )
            position.last_updated = datetime.utcnow()
        else:
            # Create new position (will need to calculate avg_entry_price from orders later)
            asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
            if not asset:
                asset = Asset(symbol=symbol, current_price=current_price)
                self.db.add(asset)
                self.db.flush()

            position = Position(
                asset_id=asset.id,
                symbol=symbol,
                quantity=quantity,
                avg_entry_price=current_price or 0.0,
                current_price=current_price,
                first_bought_at=datetime.utcnow(),
                exchange=exchange,
            )
            self.db.add(position)

        self.db.commit()
        return position

