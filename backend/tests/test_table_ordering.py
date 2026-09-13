"""Newest-first ordering for order tables and the fiat deposit ledger.

Uses an isolated in-memory SQLite database — never the project portfolio.db.
"""
from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.graphql.schema import _position_to_type
from src.models.database import Asset, Base, FiatDeposit, Order, Position
from src.services.fiat_deposits import FiatDepositService


def _memory_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _open_position(db: Session, *, symbol: str = "BTC") -> Position:
    asset = Asset(symbol=symbol, name=symbol, current_price=50_000.0)
    db.add(asset)
    db.flush()
    position = Position(
        asset_id=asset.id,
        symbol=symbol,
        quantity=1.0,
        first_bought_at=datetime(2024, 1, 1),
        exchange="binance",
        status="open",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


class FiatDepositOrderingTests(unittest.TestCase):
    def test_list_deposits_newest_first(self) -> None:
        db = _memory_session()
        older = datetime(2024, 1, 15, 10, 0, 0)
        newer = datetime(2025, 6, 1, 12, 0, 0)
        same_day_first = datetime(2025, 6, 1, 12, 0, 0)
        db.add_all(
            [
                FiatDeposit(
                    exchange="binance",
                    external_order_id="old",
                    currency="EUR",
                    amount=100.0,
                    status="Successful",
                    deposited_at=older,
                    source="api_sync",
                ),
                FiatDeposit(
                    exchange="okx",
                    external_order_id="mid",
                    currency="EUR",
                    amount=250.0,
                    status="Successful",
                    deposited_at=same_day_first,
                    source="api_sync",
                ),
                FiatDeposit(
                    exchange="okx",
                    external_order_id="new",
                    currency="EUR",
                    amount=400.0,
                    status="Successful",
                    deposited_at=newer,
                    source="manual",
                ),
            ]
        )
        db.commit()

        rows = FiatDepositService(db).list_deposits()
        self.assertEqual([r.external_order_id for r in rows], ["new", "mid", "old"])
        self.assertGreaterEqual(rows[0].deposited_at, rows[1].deposited_at)
        self.assertGreater(rows[1].deposited_at, rows[2].deposited_at)


class PositionOrderOrderingTests(unittest.TestCase):
    def test_position_orders_newest_first(self) -> None:
        db = _memory_session()
        position = _open_position(db)
        t0 = datetime(2024, 3, 1, 9, 0, 0)
        t1 = datetime(2025, 1, 10, 14, 30, 0)
        t2 = datetime(2025, 8, 20, 8, 0, 0)
        db.add_all(
            [
                Order(
                    position_id=position.id,
                    symbol="BTC",
                    type="buy",
                    quantity=0.1,
                    price=40_000.0,
                    executed_at=t0,
                    exchange="binance",
                    external_order_id="oldest",
                ),
                Order(
                    position_id=position.id,
                    symbol="BTC",
                    type="buy",
                    quantity=0.2,
                    price=45_000.0,
                    executed_at=t2,
                    exchange="binance",
                    external_order_id="newest",
                ),
                Order(
                    position_id=position.id,
                    symbol="BTC",
                    type="sell",
                    quantity=0.05,
                    price=48_000.0,
                    executed_at=t1,
                    exchange="binance",
                    external_order_id="middle",
                ),
            ]
        )
        db.commit()
        db.refresh(position)

        mapped = _position_to_type(position)
        self.assertEqual(
            [o.executed_at for o in mapped.orders],
            [t2, t1, t0],
        )
        self.assertEqual(
            [o.executed_at for o in position.orders],
            [t2, t1, t0],
        )


if __name__ == "__main__":
    unittest.main()
