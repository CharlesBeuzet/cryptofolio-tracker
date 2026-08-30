"""Tests for manual positions, valuations, NAV inclusion, and sync skip."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.models.database import Asset, Base, Position, PositionMetrics
from src.services.analyzer import PositionAnalyzerService
from src.services.assets import AssetsService
from src.services.manual_positions import (
    ManualPositionService,
    manual_cost_basis,
    manual_pnl,
    position_market_value,
)
from src.services.portfolio import PortfolioService


class ManualPositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        self.svc = ManualPositionService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _create(
        self,
        name: str = "EstateGuru",
        symbol: str = "ESTATE",
        exchange: str = "EstateGuru",
        value: Optional[float] = 1000.0,
        quantity: Optional[float] = 10.0,
        recorded_at: Optional[datetime] = None,
    ) -> Position:
        return self.svc.create(
            display_name=name,
            symbol=symbol,
            exchange=exchange,
            external_url="https://example.com",
            initial_value=value,
            initial_quantity=quantity,
            recorded_at=recorded_at,
        )

    def test_create_and_valuations_drive_value_cost_and_pnl(self) -> None:
        t0 = datetime(2026, 1, 1)
        pos = self._create(value=1000.0, quantity=10.0, recorded_at=t0)
        self.assertEqual(pos.source, "manual")
        self.assertEqual(pos.display_name, "EstateGuru")
        self.assertEqual(pos.external_url, "https://example.com")
        self.assertAlmostEqual(position_market_value(pos), 1000.0)
        self.assertAlmostEqual(manual_cost_basis(pos), 1000.0)
        self.assertAlmostEqual(manual_pnl(pos)[0], 0.0)

        later = self.svc.add_valuation(
            pos.id,
            value_amount=1200.0,
            quantity=10.0,
            recorded_at=t0 + timedelta(days=30),
        )
        self.assertAlmostEqual(position_market_value(later), 1200.0)
        self.assertAlmostEqual(manual_cost_basis(later), 1000.0)
        pnl, pct = manual_pnl(later)
        self.assertAlmostEqual(pnl, 200.0)
        self.assertAlmostEqual(pct, 20.0)
        self.assertAlmostEqual(later.quantity, 10.0)

    def test_portfolio_value_includes_latest_manual_mark(self) -> None:
        asset = Asset(symbol="BTC", name="Bitcoin", current_price=50000.0)
        self.db.add(asset)
        self.db.flush()
        synced = Position(
            asset_id=asset.id,
            symbol="BTC",
            quantity=1.0,
            first_bought_at=datetime.utcnow(),
            exchange="binance",
            status="open",
            source="synced",
        )
        self.db.add(synced)
        self.db.commit()

        self._create(value=2500.0, quantity=None)
        total = PortfolioService(self.db).get_portfolio_value()
        self.assertAlmostEqual(total, 52500.0)

    def test_sync_does_not_close_manual_positions(self) -> None:
        pos = self._create(exchange="binance", symbol="ETH", value=800.0, quantity=1.0)
        assets = AssetsService(self.db)
        result = assets._sync_positions([], "binance")
        self.db.refresh(pos)
        self.assertEqual(pos.status, "open")
        self.assertAlmostEqual(pos.quantity, 1.0)
        self.assertEqual(result["closed"], 0)

    def test_analyzer_skips_manual_positions(self) -> None:
        pos = self._create(value=100.0, quantity=1.0)
        analyzer = PositionAnalyzerService(self.db)
        self.assertEqual(analyzer.backfill_if_missing(), 0)
        self.assertEqual(analyzer.refresh_all_open_prices(), 0)
        metrics = (
            self.db.query(PositionMetrics)
            .filter(PositionMetrics.position_id == pos.id)
            .first()
        )
        self.assertIsNone(metrics)

    def test_display_name_and_url_rejected_on_synced_position(self) -> None:
        asset = Asset(symbol="ETH", name="Ether")
        self.db.add(asset)
        self.db.flush()
        synced = Position(
            asset_id=asset.id,
            symbol="ETH",
            quantity=1.0,
            first_bought_at=datetime.utcnow(),
            exchange="okx",
            status="open",
            source="synced",
        )
        self.db.add(synced)
        self.db.commit()

        with self.assertRaises(ValueError):
            self.svc.update(synced.id, display_name="Nope")

        with self.assertRaises(IntegrityError):
            synced.display_name = "Should fail"
            self.db.commit()
        self.db.rollback()

        with self.assertRaises(IntegrityError):
            synced.external_url = "https://example.com"
            self.db.commit()
        self.db.rollback()

    def test_update_and_delete_manual_only(self) -> None:
        pos = self._create()
        updated = self.svc.update(
            pos.id,
            display_name="Renamed",
            external_url="https://renamed.example",
        )
        self.assertEqual(updated.display_name, "Renamed")
        self.assertEqual(updated.external_url, "https://renamed.example")
        self.assertTrue(self.svc.delete(updated.id))
        self.assertIsNone(self.db.query(Position).filter(Position.id == updated.id).first())


if __name__ == "__main__":
    unittest.main()
