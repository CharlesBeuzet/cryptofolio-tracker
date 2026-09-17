"""Binance closed-order fetch uses myTrades (fill time), never allOrders since.

Uses mocked ccxt responses — never the live exchange or portfolio.db.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.connectors.binance import BinanceConnector


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _closed_order(
    order_id: str,
    *,
    created_ms: int,
    filled_ms: int,
    filled: float = 1.0,
    price: float = 0.0052,
    side: str = "sell",
    status: str = "closed",
) -> Dict[str, Any]:
    return {
        "id": order_id,
        "status": status,
        "side": side,
        "filled": filled,
        "average": price,
        "price": price,
        "timestamp": created_ms,
        "lastTradeTimestamp": filled_ms,
    }


def _trade(order_id: str, *, filled_ms: int, amount: float = 1.0) -> Dict[str, Any]:
    return {
        "id": f"t-{order_id}",
        "order": order_id,
        "timestamp": filled_ms,
        "amount": amount,
        "price": 0.0052,
        "side": "sell",
    }


class _RecordingExchange:
    """Stub ccxt.binance trade/order methods and record call kwargs."""

    def __init__(
        self,
        *,
        trades: Optional[List[Dict[str, Any]]] = None,
        orders: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.trades = list(trades or [])
        self.orders = dict(orders or {})
        self.my_trades_calls: List[Dict[str, Any]] = []
        self.fetch_order_calls: List[Dict[str, Any]] = []
        self.fetch_closed_orders_calls: List[Dict[str, Any]] = []

    def fetch_my_trades(self, symbol, since=None, limit=None, params=None, **kwargs):
        self.my_trades_calls.append(
            {
                "symbol": symbol,
                "since": kwargs.get("since", since),
                "limit": limit,
                "params": params or {},
            }
        )
        return list(self.trades)

    def fetch_order(self, order_id, symbol=None, params=None, **kwargs):
        self.fetch_order_calls.append(
            {"id": str(order_id), "symbol": symbol, "params": params or {}}
        )
        order = self.orders.get(str(order_id))
        if order is None:
            raise RuntimeError(f"unknown order {order_id}")
        return order

    def fetch_closed_orders(self, symbol, since=None, limit=None, params=None, **kwargs):
        self.fetch_closed_orders_calls.append(
            {
                "symbol": symbol,
                "since": kwargs.get("since", since),
                "limit": limit,
                "params": params or {},
            }
        )
        return []


class BinanceOrderHistoryTests(unittest.TestCase):
    def _connector(self, exchange: _RecordingExchange) -> BinanceConnector:
        connector = BinanceConnector({"api_key": "k", "api_secret": "s"})
        connector.exchange = exchange
        return connector

    def test_late_fill_uses_my_trades_since_not_all_orders(self):
        now = datetime.now(tz=timezone.utc)
        created = _ms(now - timedelta(days=10))
        filled = _ms(now - timedelta(hours=1))
        since_ms = _ms(now - timedelta(hours=2))
        late_fill = _closed_order(
            "20381",
            created_ms=created,
            filled_ms=filled,
            filled=20381,
            price=0.0052,
        )
        exchange = _RecordingExchange(
            trades=[_trade("20381", filled_ms=filled, amount=20381)],
            orders={"20381": late_fill},
        )
        connector = self._connector(exchange)

        rows = connector.fetch_orders_sync(
            "PUMP/USDC", since_ms=since_ms, paginate=False
        )

        self.assertEqual(len(exchange.fetch_closed_orders_calls), 0)
        self.assertEqual(len(exchange.my_trades_calls), 1)
        call = exchange.my_trades_calls[0]
        self.assertEqual(call["symbol"], "PUMP/USDC")
        self.assertEqual(call["since"], since_ms)
        self.assertNotIn("startTime", call["params"])
        self.assertEqual(call["limit"], 500)
        self.assertIsNone(call["params"].get("paginate"))

        self.assertEqual(exchange.fetch_order_calls, [
            {"id": "20381", "symbol": "PUMP/USDC", "params": {}},
        ])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_order_id"], "20381")
        self.assertEqual(rows[0]["symbol"], "PUMP")
        self.assertEqual(rows[0]["type"], "sell")
        self.assertEqual(rows[0]["quantity"], 20381)
        self.assertEqual(rows[0]["price"], 0.0052)
        self.assertEqual(
            rows[0]["executed_at"],
            datetime.fromtimestamp(filled / 1000.0, tz=timezone.utc).replace(
                tzinfo=None
            ),
        )

    def test_missing_since_fetches_recent_trades_without_start_time(self):
        exchange = _RecordingExchange(trades=[], orders={})
        connector = self._connector(exchange)

        connector.fetch_orders_sync("BTC/USDT", since_ms=None, paginate=False)

        self.assertEqual(len(exchange.my_trades_calls), 1)
        self.assertIsNone(exchange.my_trades_calls[0]["since"])
        self.assertEqual(len(exchange.fetch_order_calls), 0)
        self.assertEqual(len(exchange.fetch_closed_orders_calls), 0)

    def test_open_partial_fill_is_dropped(self):
        now = datetime.now(tz=timezone.utc)
        created = _ms(now - timedelta(days=5))
        filled = _ms(now - timedelta(minutes=10))
        open_order = _closed_order(
            "open-1",
            created_ms=created,
            filled_ms=filled,
            filled=0.4,
            status="open",
        )
        exchange = _RecordingExchange(
            trades=[_trade("open-1", filled_ms=filled, amount=0.4)],
            orders={"open-1": open_order},
        )
        connector = self._connector(exchange)

        rows = connector.fetch_orders_sync(
            "ETH/USDT", since_ms=_ms(now - timedelta(hours=2))
        )

        self.assertEqual(len(exchange.fetch_order_calls), 1)
        self.assertEqual(rows, [])

    def test_duplicate_fills_fetch_parent_order_once(self):
        now = datetime.now(tz=timezone.utc)
        filled = _ms(now - timedelta(minutes=5))
        closed = _closed_order("42", created_ms=filled - 10_000, filled_ms=filled)
        exchange = _RecordingExchange(
            trades=[
                _trade("42", filled_ms=filled - 1_000, amount=0.4),
                _trade("42", filled_ms=filled, amount=0.6),
            ],
            orders={"42": closed},
        )
        connector = self._connector(exchange)

        rows = connector.fetch_orders_sync(
            "BTC/USDT", since_ms=_ms(now - timedelta(hours=2))
        )

        self.assertEqual(len(exchange.fetch_order_calls), 1)
        self.assertEqual(rows[0]["external_order_id"], "42")

    def test_paginate_forwards_ccxt_flag_on_my_trades(self):
        exchange = _RecordingExchange(trades=[], orders={})
        connector = self._connector(exchange)

        connector.fetch_orders_sync("BTC/USDT", since_ms=1, paginate=True)

        self.assertTrue(exchange.my_trades_calls[0]["params"].get("paginate"))
        self.assertEqual(len(exchange.fetch_closed_orders_calls), 0)


if __name__ == "__main__":
    unittest.main()
