"""Data-quality gates for connector fetches and snapshot persistence.

Uses an isolated in-memory SQLite database — never the project portfolio.db.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.connectors.base import BaseConnector
from src.connectors.binance import BinanceConnector
from src.connectors.okx import OkxConnector
from src.data_quality import (
    ConnectorFetchError,
    is_valid_price,
    sanitize_balances,
    sanitize_prices,
    snapshot_skip_reason,
)
from src.models.database import Asset, Base, Position, PositionMetrics, PortfolioSnapshot
from src.services.analyzer import PositionAnalyzerService
from src.services.assets import AssetsService
from src.services.portfolio import PortfolioService


def _memory_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _open_position(
    db: Session,
    *,
    symbol: str = "BTC",
    quantity: float = 1.0,
    exchange: str = "binance",
    price: Optional[float] = 50_000.0,
) -> Position:
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        asset = Asset(symbol=symbol, name=symbol, current_price=price)
        db.add(asset)
        db.flush()
    elif price is not None:
        asset.current_price = price
    position = Position(
        asset_id=asset.id,
        symbol=symbol,
        quantity=quantity,
        first_bought_at=datetime.utcnow(),
        exchange=exchange,
        status="open",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


class _FakeConnector:
    name = "binance"

    def __init__(
        self,
        balances: Optional[List[Dict[str, Any]]] = None,
        prices: Optional[Dict[str, float]] = None,
        fail_balances: bool = False,
    ):
        self.balances = balances if balances is not None else []
        self.prices = prices if prices is not None else {}
        self.fail_balances = fail_balances

    async def fetch_balances(self) -> List[Dict[str, Any]]:
        if self.fail_balances:
            raise ConnectorFetchError("binance balances: 451")
        return list(self.balances)

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        return dict(self.prices)


class SanitizeHelpersTests(unittest.TestCase):
    def test_sanitize_prices_drops_zero_nan_and_negative(self):
        cleaned = sanitize_prices(
            {
                "BTC": 100.0,
                "ETH": 0,
                "SOL": float("nan"),
                "DOGE": -1,
                "XRP": float("inf"),
                "": 12.0,
            }
        )
        self.assertEqual(cleaned, {"BTC": 100.0})

    def test_sanitize_balances_drops_invalid_rows(self):
        cleaned = sanitize_balances(
            [
                {"symbol": "BTC", "quantity": 0.5, "exchange": "binance"},
                {"symbol": "ETH", "quantity": 0, "exchange": "binance"},
                {"symbol": "", "quantity": 1, "exchange": "binance"},
                {"quantity": 1, "exchange": "binance"},
                "not-a-row",
            ]
        )
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["symbol"], "BTC")
        self.assertEqual(cleaned[0]["quantity"], 0.5)

    def test_snapshot_skip_reason_rejects_zero_with_missing_prices(self):
        reason = snapshot_skip_reason(
            0.0,
            open_position_count=1,
            missing_price_count=1,
            last_value=10_000.0,
        )
        self.assertIsNotNone(reason)
        self.assertIn("usable price", reason)

    def test_snapshot_skip_reason_allows_valued_portfolio(self):
        self.assertIsNone(
            snapshot_skip_reason(
                12_345.0,
                open_position_count=2,
                missing_price_count=0,
                last_value=12_000.0,
            )
        )

    def test_is_valid_price_rejects_nan(self):
        self.assertFalse(is_valid_price(float("nan")))
        self.assertFalse(is_valid_price(0))
        self.assertTrue(is_valid_price(1.0))


class AssetsSyncQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_balance_fetch_does_not_close_positions(self):
        db = _memory_session()
        self.addCleanup(db.close)
        position = _open_position(db)
        svc = AssetsService(db)
        with self.assertRaises(ConnectorFetchError):
            await svc.sync_from_connector(_FakeConnector(fail_balances=True))
        db.refresh(position)
        self.assertEqual(position.status, "open")
        self.assertEqual(position.quantity, 1.0)

    async def test_successful_empty_balances_closes_positions(self):
        db = _memory_session()
        self.addCleanup(db.close)
        position = _open_position(db)
        result = await AssetsService(db).sync_from_connector(
            _FakeConnector(balances=[], prices={})
        )
        db.refresh(position)
        self.assertEqual(result["positions_closed"], 1)
        self.assertEqual(position.status, "closed")
        self.assertEqual(position.quantity, 0)

    async def test_zero_price_is_not_written_to_asset(self):
        db = _memory_session()
        self.addCleanup(db.close)
        _open_position(db, price=50_000.0)
        await AssetsService(db).sync_from_connector(
            _FakeConnector(
                balances=[
                    {"symbol": "BTC", "quantity": 1.0, "exchange": "binance"}
                ],
                prices={"BTC": 0.0, "ETH": float("nan")},
            )
        )
        asset = db.query(Asset).filter(Asset.symbol == "BTC").first()
        self.assertEqual(asset.current_price, 50_000.0)

    async def test_garbage_balance_payload_does_not_close_positions(self):
        db = _memory_session()
        self.addCleanup(db.close)
        position = _open_position(db)
        with self.assertRaises(ConnectorFetchError):
            await AssetsService(db).sync_from_connector(
                _FakeConnector(
                    balances=[{"symbol": "BTC", "quantity": 0, "exchange": "binance"}]
                )
            )
        db.refresh(position)
        self.assertEqual(position.status, "open")


class SnapshotQualityTests(unittest.TestCase):
    def test_skips_zero_snapshot_when_open_position_has_no_price(self):
        db = _memory_session()
        self.addCleanup(db.close)
        _open_position(db, price=None)
        snapshot = PortfolioService(db).record_snapshot(min_interval_hours=0)
        self.assertIsNone(snapshot)
        self.assertEqual(db.query(PortfolioSnapshot).count(), 0)

    def test_records_snapshot_when_value_is_usable(self):
        db = _memory_session()
        self.addCleanup(db.close)
        _open_position(db, quantity=2.0, price=100.0)
        snapshot = PortfolioService(db).record_snapshot(min_interval_hours=0)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.total_value, 200.0)

    def test_skips_zero_collapse_against_last_snapshot(self):
        db = _memory_session()
        self.addCleanup(db.close)
        _open_position(db, price=0.0)
        db.add(
            PortfolioSnapshot(
                total_value=9_000.0,
                timestamp=datetime.utcnow() - timedelta(hours=6),
            )
        )
        db.commit()
        snapshot = PortfolioService(db).record_snapshot(min_interval_hours=0)
        self.assertIsNone(snapshot)
        self.assertEqual(db.query(PortfolioSnapshot).count(), 1)


class AnalyzerPriceQualityTests(unittest.TestCase):
    def test_keeps_holding_value_when_price_goes_missing(self):
        db = _memory_session()
        self.addCleanup(db.close)
        position = _open_position(db, quantity=2.0, price=100.0)
        metrics = PositionMetrics(
            position_id=position.id,
            order_derived_qty=2.0,
            avg_entry_price=80.0,
            holding_value=200.0,
            unrealised_pnl=40.0,
            unrealised_pnl_percent=25.0,
        )
        db.add(metrics)
        db.commit()

        PositionAnalyzerService(db).refresh_market_metrics(position.id, None)
        db.refresh(metrics)
        self.assertEqual(metrics.holding_value, 200.0)
        self.assertEqual(metrics.unrealised_pnl, 40.0)

    def test_zero_price_does_not_wipe_unrealised_pnl(self):
        db = _memory_session()
        self.addCleanup(db.close)
        position = _open_position(db, quantity=1.0, price=100.0)
        metrics = PositionMetrics(
            position_id=position.id,
            order_derived_qty=1.0,
            avg_entry_price=80.0,
            holding_value=100.0,
            unrealised_pnl=20.0,
        )
        db.add(metrics)
        db.commit()
        PositionAnalyzerService(db).refresh_market_metrics(position.id, 0.0)
        db.refresh(metrics)
        self.assertEqual(metrics.holding_value, 100.0)


class ConnectorFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_binance_balances_raise_instead_of_empty_list(self):
        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})

        class Boom:
            def fetch_balance(self):
                raise RuntimeError("451 Unavailable For Legal Reasons")

        connector.exchange = Boom()
        with self.assertRaises(ConnectorFetchError):
            await connector.fetch_balances()

    async def test_binance_empty_total_is_a_successful_empty_book(self):
        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})

        class Empty:
            def fetch_balance(self):
                return {"total": {}}

        connector.exchange = Empty()
        self.assertEqual(await connector.fetch_balances(), [])

    async def test_binance_ignores_zero_ticker(self):
        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})

        class Tick:
            def fetch_ticker(self, pair):
                return {"last": 0}

        connector.exchange = Tick()
        self.assertEqual(await connector.fetch_prices(["BTC"]), {})

    async def test_okx_raises_if_one_wallet_type_fails(self):
        connector = OkxConnector(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"}
        )

        class Partial:
            def fetch_balance(self, params=None):
                account = (params or {}).get("type")
                if account == "trading":
                    raise RuntimeError("timeout")
                return {"total": {"BTC": 1.0}}

        connector.exchange = Partial()
        with self.assertRaises(ConnectorFetchError):
            await connector.fetch_balances()

    def test_ohlcv_failure_with_no_candles_raises(self):
        class Stub(BaseConnector):
            async def fetch_balances(self):
                return []

            async def fetch_orders(self, symbol=None):
                return []

            async def fetch_prices(self, symbols):
                return {}

            async def test_connection(self):
                return True

        class BoomExchange:
            def fetch_ohlcv(self, *args, **kwargs):
                raise RuntimeError("network down")

        stub = Stub({})
        stub.exchange = BoomExchange()
        with self.assertRaises(ConnectorFetchError):
            stub.fetch_price_history_sync("BTC/USDT", since_ms=0, days=1)


if __name__ == "__main__":
    unittest.main()
