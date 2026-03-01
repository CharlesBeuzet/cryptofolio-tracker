"""GraphQL schema definitions."""
from datetime import datetime
from typing import List, Optional
import strawberry
from strawberry.fastapi import GraphQLRouter

from ..models.database import Position, Order, PortfolioSnapshot, Asset, SessionLocal
from ..services.portfolio import PortfolioService


@strawberry.type
class AssetType:
    """Asset GraphQL type."""
    id: int
    symbol: str
    name: Optional[str]
    current_price: Optional[float]
    last_updated: datetime


@strawberry.type
class OrderType:
    """Order GraphQL type."""
    id: int
    symbol: str
    type: str
    quantity: float
    price: float
    executed_at: datetime
    exchange: Optional[str]


@strawberry.type
class PositionType:
    """Position GraphQL type."""
    id: int
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: Optional[float]
    pnl: Optional[float]
    pnl_percent: Optional[float]
    first_bought_at: datetime
    exchange: Optional[str]
    orders: List[OrderType]

    @strawberry.field
    def value(self) -> float:
        """Calculate position value."""
        if self.current_price:
            return self.quantity * self.current_price
        return 0.0

    @strawberry.field
    def duration_days(self) -> int:
        """Calculate position duration in days."""
        delta = datetime.utcnow() - self.first_bought_at
        return delta.days


@strawberry.type
class PortfolioSnapshotType:
    """Portfolio snapshot GraphQL type."""
    id: int
    total_value: float
    timestamp: datetime


@strawberry.type
class DailyPnlType:
    """Daily P&L GraphQL type."""
    date: str
    pnl: float
    pnl_percent: float


@strawberry.type
class PortfolioType:
    """Portfolio GraphQL type."""
    total_value: float
    todays_pnl: float
    todays_pnl_percent: float
    positions: List[PositionType]


@strawberry.type
class PerformanceMetricsType:
    """Performance metrics GraphQL type."""
    total_value: float
    todays_pnl: float
    todays_pnl_percent: float


@strawberry.type
class Query:
    """GraphQL query root."""

    @strawberry.field
    def portfolio(self) -> PortfolioType:
        """Get portfolio overview."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            pnl_data = service.get_todays_pnl()
            positions = service.get_positions()

            # Convert positions to GraphQL types
            position_types = []
            for pos in positions:
                orders = [
                    OrderType(
                        id=o.id,
                        symbol=o.symbol,
                        type=o.type,
                        quantity=o.quantity,
                        price=o.price,
                        executed_at=o.executed_at,
                        exchange=o.exchange,
                    )
                    for o in pos.orders
                ]
                position_types.append(
                    PositionType(
                        id=pos.id,
                        symbol=pos.symbol,
                        quantity=pos.quantity,
                        avg_entry_price=pos.avg_entry_price,
                        current_price=pos.current_price,
                        pnl=pos.pnl,
                        pnl_percent=pos.pnl_percent,
                        first_bought_at=pos.first_bought_at,
                        exchange=pos.exchange,
                        orders=orders,
                    )
                )

            return PortfolioType(
                total_value=pnl_data["value"],
                todays_pnl=pnl_data["pnl"],
                todays_pnl_percent=pnl_data["pnl_percent"],
                positions=position_types,
            )
        finally:
            db.close()

    @strawberry.field
    def positions(self) -> List[PositionType]:
        """Get all positions."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            positions = service.get_positions()

            position_types = []
            for pos in positions:
                orders = [
                    OrderType(
                        id=o.id,
                        symbol=o.symbol,
                        type=o.type,
                        quantity=o.quantity,
                        price=o.price,
                        executed_at=o.executed_at,
                        exchange=o.exchange,
                    )
                    for o in pos.orders
                ]
                position_types.append(
                    PositionType(
                        id=pos.id,
                        symbol=pos.symbol,
                        quantity=pos.quantity,
                        avg_entry_price=pos.avg_entry_price,
                        current_price=pos.current_price,
                        pnl=pos.pnl,
                        pnl_percent=pos.pnl_percent,
                        first_bought_at=pos.first_bought_at,
                        exchange=pos.exchange,
                        orders=orders,
                    )
                )

            return position_types
        finally:
            db.close()

    @strawberry.field
    def position(self, id: int) -> Optional[PositionType]:
        """Get a specific position by ID."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            pos = service.get_position_by_id(id)
            if not pos:
                return None

            orders = [
                OrderType(
                    id=o.id,
                    symbol=o.symbol,
                    type=o.type,
                    quantity=o.quantity,
                    price=o.price,
                    executed_at=o.executed_at,
                    exchange=o.exchange,
                )
                for o in pos.orders
            ]

            return PositionType(
                id=pos.id,
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_entry_price=pos.avg_entry_price,
                current_price=pos.current_price,
                pnl=pos.pnl,
                pnl_percent=pos.pnl_percent,
                first_bought_at=pos.first_bought_at,
                exchange=pos.exchange,
                orders=orders,
            )
        finally:
            db.close()

    @strawberry.field
    def performance(self) -> PerformanceMetricsType:
        """Get performance metrics."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            pnl_data = service.get_todays_pnl()
            return PerformanceMetricsType(
                total_value=pnl_data["value"],
                todays_pnl=pnl_data["pnl"],
                todays_pnl_percent=pnl_data["pnl_percent"],
            )
        finally:
            db.close()

    @strawberry.field
    def portfolio_history(self, days: int = 180) -> List[PortfolioSnapshotType]:
        """Get portfolio value history."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            history = service.get_portfolio_history(days)
            return [
                PortfolioSnapshotType(
                    id=0,  # Not used in response
                    total_value=h["value"],
                    timestamp=h["timestamp"],
                )
                for h in history
            ]
        finally:
            db.close()

    @strawberry.field
    def daily_pnl_history(self, days: int = 30) -> List[DailyPnlType]:
        """Get daily P&L history."""
        db = SessionLocal()
        try:
            service = PortfolioService(db)
            history = service.get_daily_pnl_history(days)
            return [
                DailyPnlType(
                    date=h["date"].isoformat(),
                    pnl=h["pnl"],
                    pnl_percent=h["pnl_percent"],
                )
                for h in history
            ]
        finally:
            db.close()


schema = strawberry.Schema(query=Query)

