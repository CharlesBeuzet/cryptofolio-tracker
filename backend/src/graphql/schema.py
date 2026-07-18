"""GraphQL schema definitions."""
from datetime import datetime
from typing import List, Optional
import strawberry
from strawberry.fastapi import GraphQLRouter

from ..models.database import Position, Order, PortfolioSnapshot, Asset, PositionMetrics, SessionLocal
from ..services.portfolio import PortfolioService
from ..services.fiat_deposits import FiatDepositService
from ..services.price_history import PriceHistoryService
from ..services.metrics_helpers import cost_basis, cash_in_trade


@strawberry.type
class CoinGeckoCandidateType:
    """One CoinGecko listing that shares a ticker symbol."""

    id: str
    name: str
    symbol: str


@strawberry.type
class PricePointType:
    """Single OHLC price candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    price: float


@strawberry.type
class AssetPriceHistoryType:
    """Market price history for one asset (not persisted)."""

    symbol: str
    days: int
    is_mock: bool
    resolution_status: str
    ambiguity_message: Optional[str]
    candidates: List[CoinGeckoCandidateType]
    points: List[PricePointType]


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
class PositionMetricsType:
    """Order-derived position analytics."""

    avg_entry_price: float
    avg_exit_price: Optional[float]
    break_even_price: float
    realised_pnl: float
    realised_pnl_percent: float
    unrealised_pnl: float
    unrealised_pnl_percent: float
    total_pnl: float
    total_pnl_percent: float
    holding_value: float
    order_derived_qty: float
    total_buy_cost: float
    total_sell_proceeds: float
    cost_basis: float
    cash_in_trade: float
    metrics_updated_at: datetime


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
    status: str
    orders: List[OrderType]
    metrics: Optional[PositionMetricsType]

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


def _metrics_to_type(metrics: PositionMetrics) -> PositionMetricsType:
    return PositionMetricsType(
        avg_entry_price=metrics.avg_entry_price,
        avg_exit_price=metrics.avg_exit_price,
        break_even_price=metrics.break_even_price,
        realised_pnl=metrics.realised_pnl,
        realised_pnl_percent=metrics.realised_pnl_percent,
        unrealised_pnl=metrics.unrealised_pnl,
        unrealised_pnl_percent=metrics.unrealised_pnl_percent,
        total_pnl=metrics.total_pnl,
        total_pnl_percent=metrics.total_pnl_percent,
        holding_value=metrics.holding_value,
        order_derived_qty=metrics.order_derived_qty,
        total_buy_cost=metrics.total_buy_cost,
        total_sell_proceeds=metrics.total_sell_proceeds,
        cost_basis=cost_basis(metrics),
        cash_in_trade=cash_in_trade(metrics),
        metrics_updated_at=metrics.metrics_updated_at,
    )


def _position_to_type(pos: Position) -> PositionType:
    """Map a Position ORM object to GraphQL type."""
    asset_price = pos.asset.current_price if pos.asset else None
    metrics = pos.metrics
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
        avg_entry_price=metrics.avg_entry_price if metrics else 0.0,
        current_price=asset_price,
        pnl=metrics.unrealised_pnl if metrics else 0.0,
        pnl_percent=metrics.unrealised_pnl_percent if metrics else 0.0,
        first_bought_at=pos.first_bought_at,
        exchange=pos.exchange,
        status=pos.status,
        orders=orders,
        metrics=_metrics_to_type(metrics) if metrics else None,
    )


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
class FiatCurrencyTotalType:
    """Aggregated fiat injected for one currency (fiat units, not USD converted)."""

    currency: str
    total_amount: float


@strawberry.type
class FiatDepositsSummaryType:
    """Roll-up of fiat injections for the dashboard home."""

    totals_by_currency: List[FiatCurrencyTotalType]
    included_record_count: int


@strawberry.type
class FiatDepositRecordType:
    """Single fiat deposit / injection row."""

    id: int
    exchange: str
    external_order_id: Optional[str]
    currency: str
    amount: float
    fee: Optional[float]
    status: Optional[str]
    method: Optional[str]
    source: str
    deposited_at: datetime
    created_at: datetime


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

            position_types = [_position_to_type(pos) for pos in positions]

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
            return [_position_to_type(pos) for pos in positions]
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

            return _position_to_type(pos)
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
        """Get portfolio value history (days <= 0 = Max / all snapshots)."""
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

    @strawberry.field
    def fiat_deposits_summary(self) -> FiatDepositsSummaryType:
        """Summarize fiat injected (successful synced deposits + all manual rows)."""
        db = SessionLocal()
        try:
            svc = FiatDepositService(db)
            data = svc.get_summary()
            return FiatDepositsSummaryType(
                totals_by_currency=[
                    FiatCurrencyTotalType(currency=r["currency"], total_amount=r["total_amount"])
                    for r in data["totals_by_currency"]
                ],
                included_record_count=data["included_record_count"],
            )
        finally:
            db.close()

    @strawberry.field
    def fiat_deposits(self, limit: int = 500) -> List[FiatDepositRecordType]:
        """List fiat deposit records, newest first."""
        db = SessionLocal()
        try:
            svc = FiatDepositService(db)
            rows = svc.list_deposits(limit=limit)
            return [
                FiatDepositRecordType(
                    id=r.id,
                    exchange=r.exchange,
                    external_order_id=r.external_order_id,
                    currency=r.currency,
                    amount=r.amount,
                    fee=r.fee,
                    status=r.status,
                    method=r.method,
                    source=r.source,
                    deposited_at=r.deposited_at,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        finally:
            db.close()

    @strawberry.field
    async def asset_price_history(
        self,
        symbol: str,
        days: int = 90,
        exchange: Optional[str] = None,
    ) -> AssetPriceHistoryType:
        """Fetch USDT price history from the position's exchange (in-memory cache only).

        days <= 0 means Max (capped exchange lookback).
        """
        service = PriceHistoryService()
        result = await service.fetch(symbol, days, exchange)
        return AssetPriceHistoryType(
            symbol=symbol.upper(),
            days=days,
            is_mock=result.is_mock,
            resolution_status=result.resolution_status,
            ambiguity_message=result.ambiguity_message,
            candidates=[
                CoinGeckoCandidateType(id=c.id, name=c.name, symbol=c.symbol)
                for c in result.candidates
            ],
            points=[
                PricePointType(
                    timestamp=row["timestamp"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    price=row["price"],
                )
                for row in result.points
            ],
        )


schema = strawberry.Schema(query=Query)

