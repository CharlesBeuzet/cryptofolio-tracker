"""Order sync: generic recent/archive connector contract.

Uses an isolated in-memory SQLite database — never the project portfolio.db.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.connectors.base import BaseConnector, market_pairs_for
from src.connectors.okx import OkxConnector
from src.models.database import Asset, Base, Order, Position
from src.services.orders import OrderService
from src.utils.data_quality import ConnectorFetchError


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
    symbol: str,
    exchange: str,
    price: float = 1.0,
) -> Position:
    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
    if not asset:
        asset = Asset(symbol=symbol, name=symbol, current_price=price)
        db.add(asset)
        db.flush()
    position = Position(
        asset_id=asset.id,
        symbol=symbol,
        quantity=1.0,
        first_bought_at=datetime.utcnow(),
        exchange=exchange,
        status="open",
        source="synced",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


class _RecordingConnector:
    """Minimal connector double: same methods OrderService calls."""

    def __init__(
        self,
        name: str,
        recent: List[Dict[str, Any]] | None = None,
        archived: List[Dict[str, Any]] | None = None,
    ):
        self.name = name
        self.recent = recent or []
        self.archived = archived or []
        self.recent_calls: List[List[str]] = []
        self.archived_calls: List[List[str]] = []

    def fetch_recent_orders_sync(
        self, symbols: Sequence[str]
    ) -> List[Dict[str, Any]]:
        self.recent_calls.append(list(symbols))
        return list(self.recent)

    def fetch_archived_orders_sync(
        self, symbols: Sequence[str]
    ) -> List[Dict[str, Any]]:
        self.archived_calls.append(list(symbols))
        return list(self.archived)


def _order_row(
    *,
    ext_id: str,
    symbol: str,
    exchange: str,
    executed_at: datetime,
    quantity: float = 100.0,
    price: float = 0.0052,
    side: str = "sell",
) -> Dict[str, Any]:
    return {
        "external_order_id": ext_id,
        "symbol": symbol,
        "type": side,
        "quantity": quantity,
        "price": price,
        "executed_at": executed_at,
        "exchange": exchange,
    }


class MarketPairsTests(unittest.TestCase):
    def test_expands_base_to_usdt_and_usdc(self):
        self.assertEqual(market_pairs_for("PUMP"), ["PUMP/USDT", "PUMP/USDC"])

    def test_keeps_qualified_pair(self):
        self.assertEqual(market_pairs_for("PUMP/USDC"), ["PUMP/USDC"])


class OrderServiceSyncTests(unittest.TestCase):
    def setUp(self):
        self.db = _memory_session()
        self.addCleanup(self.db.close)
        self.svc = OrderService(self.db)

    def test_skips_when_no_open_positions(self):
        connector = _RecordingConnector("okx")
        self.assertEqual(self.svc.sync_all_orders_from_connector(connector), 0)
        self.assertEqual(connector.recent_calls, [])
        self.assertEqual(connector.archived_calls, [])

    def test_cold_start_uses_archive_not_recent(self):
        _open_position(self.db, symbol="PUMP", exchange="okx")
        placed = datetime(2026, 8, 22, 14, 22)
        fills = [
            _order_row(
                ext_id="1",
                symbol="PUMP",
                exchange="okx",
                executed_at=placed + timedelta(hours=2),
                quantity=20381,
            ),
            _order_row(
                ext_id="2",
                symbol="PUMP",
                exchange="okx",
                executed_at=placed + timedelta(hours=5),
                quantity=10000,
            ),
            _order_row(
                ext_id="3",
                symbol="PUMP",
                exchange="okx",
                executed_at=placed + timedelta(hours=18),
                quantity=20381,
                price=0.0052,
            ),
        ]
        connector = _RecordingConnector("okx", archived=fills)
        added = self.svc.sync_all_orders_from_connector(connector)
        self.assertEqual(added, 3)
        self.assertEqual(len(connector.archived_calls), 1)
        self.assertEqual(connector.archived_calls[0], ["PUMP"])
        self.assertEqual(connector.recent_calls, [])
        ids = {o.external_order_id for o in self.db.query(Order).all()}
        self.assertEqual(ids, {"1", "2", "3"})

    def test_incremental_uses_recent_and_is_idempotent(self):
        position = _open_position(self.db, symbol="PUMP", exchange="okx")
        existing_at = datetime(2026, 8, 22, 16, 42)
        self.db.add(
            Order(
                position_id=position.id,
                symbol="PUMP",
                type="sell",
                quantity=10000,
                price=0.005,
                executed_at=existing_at,
                exchange="okx",
                external_order_id="1",
            )
        )
        self.db.commit()

        late_fill = _order_row(
            ext_id="3",
            symbol="PUMP",
            exchange="okx",
            executed_at=datetime(2026, 8, 23, 8, 52),
            quantity=20381,
            price=0.0052,
        )
        already = _order_row(
            ext_id="1",
            symbol="PUMP",
            exchange="okx",
            executed_at=existing_at,
            quantity=10000,
            price=0.005,
        )
        connector = _RecordingConnector("okx", recent=[already, late_fill])
        added = self.svc.sync_all_orders_from_connector(connector)
        self.assertEqual(added, 1)
        self.assertEqual(len(connector.recent_calls), 1)
        self.assertEqual(connector.archived_calls, [])
        self.assertEqual(self.db.query(Order).count(), 2)

        added_again = self.svc.sync_all_orders_from_connector(connector)
        self.assertEqual(added_again, 0)
        self.assertEqual(self.db.query(Order).count(), 2)

    def test_attaches_only_to_matching_open_positions(self):
        _open_position(self.db, symbol="PUMP", exchange="okx")
        connector = _RecordingConnector(
            "okx",
            archived=[
                _order_row(
                    ext_id="pump-1",
                    symbol="PUMP",
                    exchange="okx",
                    executed_at=datetime.utcnow(),
                ),
                _order_row(
                    ext_id="btc-1",
                    symbol="BTC",
                    exchange="okx",
                    executed_at=datetime.utcnow(),
                ),
            ],
        )
        added = self.svc.sync_all_orders_from_connector(connector)
        self.assertEqual(added, 1)
        self.assertEqual(self.db.query(Order).one().symbol, "PUMP")

    def test_binance_path_is_the_same_call(self):
        _open_position(self.db, symbol="ETH", exchange="binance")
        connector = _RecordingConnector(
            "binance",
            archived=[
                _order_row(
                    ext_id="b1",
                    symbol="ETH",
                    exchange="binance",
                    executed_at=datetime.utcnow(),
                    side="buy",
                    quantity=0.5,
                    price=3000.0,
                )
            ],
        )
        added = self.svc.sync_all_orders_from_connector(connector)
        self.assertEqual(added, 1)
        self.assertEqual(connector.archived_calls[0], ["ETH"])
        self.assertEqual(connector.recent_calls, [])


class DefaultConnectorOrderFetchTests(unittest.TestCase):
    def test_base_defaults_return_empty(self):
        class Stub(BaseConnector):
            async def fetch_balances(self):
                return []

            async def fetch_orders(self, symbol=None):
                return []

            async def fetch_prices(self, symbols):
                return {}

            async def test_connection(self):
                return True

        stub = Stub({})
        self.assertEqual(stub.fetch_recent_orders_sync(["BTC"]), [])
        self.assertEqual(stub.fetch_archived_orders_sync(["BTC"]), [])
        self.assertFalse(hasattr(stub, "supports_account_wide_order_fetch"))


class OkxHistoryNormalizationTests(unittest.TestCase):
    def test_filled_spot_row_uses_base_symbol_and_fill_time(self):
        connector = OkxConnector(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"}
        )
        filled_ms = int(datetime(2026, 8, 23, 8, 52).timestamp() * 1000)
        row = connector._normalize_raw_okx_order(
            {
                "ordId": "20381",
                "instId": "PUMP-USDC",
                "state": "filled",
                "side": "sell",
                "fillSz": "20381",
                "avgPx": "0.0052",
                "uTime": str(filled_ms),
                "cTime": str(filled_ms - 86_400_000),
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["external_order_id"], "20381")
        self.assertEqual(row["symbol"], "PUMP")
        self.assertEqual(row["type"], "sell")
        self.assertEqual(row["quantity"], 20381.0)
        self.assertEqual(row["price"], 0.0052)

    def test_unfilled_row_is_dropped(self):
        connector = OkxConnector(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"}
        )
        self.assertIsNone(
            connector._normalize_raw_okx_order(
                {
                    "ordId": "1",
                    "instId": "PUMP-USDC",
                    "state": "canceled",
                    "side": "sell",
                    "fillSz": "0",
                    "avgPx": "0.0052",
                }
            )
        )

    def test_account_wide_history_paginates_without_begin(self):
        connector = OkxConnector(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"}
        )
        pages = [
            {
                "code": "0",
                "data": [
                    {
                        "ordId": str(i),
                        "instId": "PUMP-USDC",
                        "state": "filled",
                        "side": "sell",
                        "fillSz": "1",
                        "avgPx": "0.01",
                        "uTime": "1690000000000",
                    }
                    for i in range(100)
                ],
            },
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "late",
                        "instId": "PUMP-USDC",
                        "state": "filled",
                        "side": "sell",
                        "fillSz": "20381",
                        "avgPx": "0.0052",
                        "uTime": "1690000000000",
                    }
                ],
            },
        ]
        calls: List[Dict[str, Any]] = []

        class Exchange:
            def request(self, path, api, method, params):
                calls.append({"path": path, "params": dict(params)})
                return pages[len(calls) - 1]

        connector.exchange = Exchange()
        rows = connector.fetch_recent_orders_sync(["PUMP", "BTC"])
        self.assertEqual(len(rows), 101)
        self.assertEqual(calls[0]["path"], "trade/orders-history")
        self.assertNotIn("begin", calls[0]["params"])
        self.assertNotIn("instId", calls[0]["params"])
        self.assertEqual(calls[0]["params"]["instType"], "SPOT")
        self.assertEqual(calls[1]["params"]["after"], "99")

        calls.clear()
        connector.fetch_archived_orders_sync(["PUMP"])
        self.assertEqual(calls[0]["path"], "trade/orders-history-archive")
        self.assertNotIn("begin", calls[0]["params"])


class BinanceSymbolLoopTests(unittest.TestCase):
    def test_recent_fetch_loops_quote_pairs_and_skips_unknown(self):
        from src.connectors.binance import BinanceConnector

        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})
        seen_pairs: List[str] = []

        def fake_sync(market_pair, since_ms, *, limit=500, paginate=False):
            seen_pairs.append(market_pair)
            if market_pair.endswith("/USDT"):
                raise ConnectorFetchError(
                    "binance orders for PUMP/USDT: invalid symbol"
                )
            return [
                _order_row(
                    ext_id="usdc-1",
                    symbol="PUMP",
                    exchange="binance",
                    executed_at=datetime.utcnow(),
                )
            ]

        connector.fetch_orders_sync = fake_sync  # type: ignore[method-assign]
        rows = connector.fetch_recent_orders_sync(["PUMP"])
        self.assertEqual(seen_pairs, ["PUMP/USDT", "PUMP/USDC"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_order_id"], "usdc-1")

    def test_recent_fetch_only_loops_caller_symbols(self):
        from src.connectors.binance import BinanceConnector

        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})
        seen_bases: List[str] = []

        def fake_sync(market_pair, since_ms, *, limit=500, paginate=False):
            seen_bases.append(market_pair.split("/")[0])
            return []

        connector.fetch_orders_sync = fake_sync  # type: ignore[method-assign]
        connector.fetch_recent_orders_sync(["BTC", "ETH"])
        self.assertEqual(set(seen_bases), {"BTC", "ETH"})


if __name__ == "__main__":
    unittest.main()
