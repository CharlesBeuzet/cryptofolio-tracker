"""OKX closed-order fetch uses 7-day history per pair, never cTime `since`.

Uses mocked ccxt responses — never the live exchange or portfolio.db.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.connectors.okx import (
    OkxConnector,
    _OKX_ORDER_PAGE_LIMIT,
    _OKX_ORDERS_HISTORY,
    _OKX_ORDERS_HISTORY_ARCHIVE,
)


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
) -> Dict[str, Any]:
    return {
        "id": order_id,
        "status": "closed",
        "side": side,
        "filled": filled,
        "average": price,
        "price": price,
        "timestamp": created_ms,
        "lastTradeTimestamp": filled_ms,
    }


class _RecordingExchange:
    """Stub ccxt.okx.fetch_closed_orders and record call kwargs."""

    def __init__(self, pages: Optional[List[List[Dict[str, Any]]]] = None) -> None:
        self.pages = list(pages or [])
        self.calls: List[Dict[str, Any]] = []

    def fetch_closed_orders(self, symbol, since=None, limit=None, params=None, **kwargs):
        self.calls.append(
            {
                "symbol": symbol,
                "since": kwargs.get("since", since),
                "limit": limit,
                "params": params or {},
            }
        )
        if self.pages:
            return self.pages.pop(0)
        return []


class OkxOrderHistoryTests(unittest.TestCase):
    def _connector(self, exchange: _RecordingExchange) -> OkxConnector:
        connector = OkxConnector(
            {"api_key": "k", "api_secret": "s", "passphrase": "p"}
        )
        connector.exchange = exchange
        return connector

    def test_fetch_orders_sync_omits_since_and_uses_history_endpoint(self):
        now = datetime.now(tz=timezone.utc)
        created = _ms(now - timedelta(days=10))
        filled = _ms(now - timedelta(hours=1))
        late_fill = _closed_order(
            "20381",
            created_ms=created,
            filled_ms=filled,
            filled=20381,
            price=0.0052,
        )
        exchange = _RecordingExchange(pages=[[late_fill]])
        connector = self._connector(exchange)

        # Cursor derived from a sibling fill — historically sent as OKX begin.
        since_ms = _ms(now - timedelta(hours=2))
        rows = connector.fetch_orders_sync(
            "PUMP/USDC", since_ms=since_ms, paginate=False
        )

        self.assertEqual(len(exchange.calls), 1)
        call = exchange.calls[0]
        self.assertEqual(call["symbol"], "PUMP/USDC")
        self.assertIsNone(call["since"])
        self.assertNotIn("since", call["params"])
        self.assertNotIn("begin", call["params"])
        self.assertEqual(call["params"].get("method"), _OKX_ORDERS_HISTORY)
        self.assertIsNone(call["params"].get("paginate"))
        self.assertEqual(call["limit"], _OKX_ORDER_PAGE_LIMIT)

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

    def test_old_since_switches_to_archive_without_begin(self):
        exchange = _RecordingExchange(pages=[[]])
        connector = self._connector(exchange)
        nine_days_ms = 9 * 24 * 60 * 60 * 1000
        now_ms = _ms(datetime.now(tz=timezone.utc))

        connector.fetch_orders_sync(
            "BTC/USDT", since_ms=now_ms - nine_days_ms, paginate=False
        )

        self.assertEqual(len(exchange.calls), 1)
        call = exchange.calls[0]
        self.assertEqual(call["params"].get("method"), _OKX_ORDERS_HISTORY_ARCHIVE)
        self.assertIsNone(call["since"])
        self.assertNotIn("since", call["params"])
        self.assertNotIn("begin", call["params"])

    def test_missing_since_stays_on_seven_day_history(self):
        exchange = _RecordingExchange(pages=[[]])
        connector = self._connector(exchange)

        connector.fetch_orders_sync("BTC/USDT", since_ms=None, paginate=False)

        self.assertEqual(len(exchange.calls), 1)
        self.assertEqual(
            exchange.calls[0]["params"].get("method"), _OKX_ORDERS_HISTORY
        )
        self.assertIsNone(exchange.calls[0]["since"])

    def test_paginate_walks_ordid_after_without_since(self):
        # ccxt sorts by timestamp ascending, so page[0] is the oldest order.
        # OKX `after` cursor retrieves records earlier than the given ordId.
        page1 = [
            _closed_order(str(i), created_ms=1, filled_ms=2) for i in range(100)
        ]
        page2 = [_closed_order("last", created_ms=1, filled_ms=2)]
        exchange = _RecordingExchange(pages=[page1, page2])
        connector = self._connector(exchange)
        recent_since = _ms(datetime.now(tz=timezone.utc) - timedelta(hours=1))

        rows = connector.fetch_orders_sync(
            "ETH/USDT", since_ms=recent_since, paginate=True
        )

        self.assertEqual(len(exchange.calls), 2)
        self.assertIsNone(exchange.calls[0]["since"])
        self.assertIsNone(exchange.calls[1]["since"])
        self.assertNotIn("after", exchange.calls[0]["params"])
        # page[0] is the oldest order (ccxt sorts ascending by timestamp).
        self.assertEqual(exchange.calls[1]["params"].get("after"), "0")
        self.assertEqual(
            exchange.calls[1]["params"].get("method"),
            _OKX_ORDERS_HISTORY,
        )
        self.assertEqual(len(rows), 101)
        self.assertEqual(rows[-1]["external_order_id"], "last")


if __name__ == "__main__":
    unittest.main()
