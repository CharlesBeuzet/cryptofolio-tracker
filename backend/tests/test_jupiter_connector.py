"""Jupiter Solana connector unit tests (mocked HTTP — no live APIs / portfolio.db)."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from src.connectors.jupiter import (
    SOL_MINT,
    USDC_MINT,
    JupiterConnector,
)
from src.utils.data_quality import ConnectorFetchError

PUMP_MINT = "6SUryVEuDz5hqAxab6QrGfbzWvjN8dC7m29ezSvDpump"


class _FakeHttp:
    """Route JupiterConnector._request_json calls to canned payloads."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
        self.holdings: Dict[str, Any] = {
            "amount": "1000000000",
            "uiAmount": 1.0,
            "uiAmountString": "1",
            "tokens": {
                PUMP_MINT: [
                    {
                        "account": "ata1",
                        "amount": "5000000",
                        "uiAmount": 5.0,
                        "uiAmountString": "5",
                        "decimals": 6,
                        "isFrozen": False,
                        "isAssociatedTokenAccount": True,
                    }
                ],
                USDC_MINT: [
                    {
                        "account": "ata2",
                        "amount": "10000000",
                        "uiAmount": 10.0,
                        "uiAmountString": "10",
                        "decimals": 6,
                        "isFrozen": False,
                        "isAssociatedTokenAccount": True,
                    }
                ],
            },
        }
        self.search: List[Dict[str, Any]] = [
            {
                "id": SOL_MINT,
                "symbol": "SOL",
                "name": "Wrapped SOL",
                "decimals": 9,
                "usdPrice": 100.0,
            },
            {
                "id": PUMP_MINT,
                "symbol": "PUMP",
                "name": "Pump",
                "decimals": 6,
                "usdPrice": 0.05,
            },
            {
                "id": USDC_MINT,
                "symbol": "USDC",
                "name": "USD Coin",
                "decimals": 6,
                "usdPrice": 1.0,
            },
        ]
        self.prices: Dict[str, Any] = {
            SOL_MINT: {"usdPrice": 100.0, "decimals": 9, "liquidity": 1, "createdAt": "x"},
            PUMP_MINT: {"usdPrice": 0.05, "decimals": 6, "liquidity": 1, "createdAt": "x"},
            USDC_MINT: {"usdPrice": 1.0, "decimals": 6, "liquidity": 1, "createdAt": "x"},
        }
        self.orders_pages: List[Dict[str, Any]] = [
            {
                "orders": [
                    {
                        "orderKey": "order-1",
                        "status": "Completed",
                        "inputMint": SOL_MINT,
                        "outputMint": PUMP_MINT,
                        "trades": [
                            {
                                "orderKey": "order-1",
                                "action": "Fill",
                                "inputMint": SOL_MINT,
                                "outputMint": PUMP_MINT,
                                "inputAmount": "2.0",
                                "outputAmount": "4000.0",
                                "txId": "tx-buy-1",
                                "confirmedAt": "2024-07-21T03:07:19Z",
                            }
                        ],
                    },
                    {
                        "orderKey": "order-2",
                        "status": "Completed",
                        "inputMint": PUMP_MINT,
                        "outputMint": USDC_MINT,
                        "trades": [
                            {
                                "orderKey": "order-2",
                                "action": "Fill",
                                "inputMint": PUMP_MINT,
                                "outputMint": USDC_MINT,
                                "inputAmount": "100.0",
                                "outputAmount": "5.0",
                                "txId": "tx-sell-1",
                                "confirmedAt": "2024-07-22T01:00:00Z",
                            }
                        ],
                    },
                ],
                "totalPages": 1,
                "page": 1,
            }
        ]
        self.coingecko: Dict[str, Any] = {
            "prices": [
                [1_721_000_000_000, 0.04],
                [1_721_000_360_000, 0.045],
            ]
        }

    def __call__(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        self.calls.append((method, path, params))
        if "holdings" in path:
            return self.holdings
        if path.endswith("tokens/v2/search") or path.endswith("ultra/v1/search"):
            return list(self.search)
        if path.rstrip("/").endswith("price/v3") or path == "price/v3":
            ids = str((params or {}).get("ids") or "").split(",")
            return {mint: self.prices[mint] for mint in ids if mint in self.prices}
        if "getTriggerOrders" in path:
            page = int((params or {}).get("page") or 1)
            if page <= len(self.orders_pages):
                return self.orders_pages[page - 1]
            return {"orders": [], "totalPages": len(self.orders_pages), "page": page}
        if "market_chart" in path:
            return self.coingecko
        raise AssertionError(f"unexpected request {method} {path} params={params}")


class JupiterConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = JupiterConnector(
            {
                "address": "ErJKdNoarixqGGQTHbBtvHtg2nkcCqcKtYjGbVKUxY7D",
                "hostname": "https://api.jup.ag",
            }
        )
        self.http = _FakeHttp()
        self._patcher = patch.object(
            self.connector, "_request_json", side_effect=self.http
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_fetch_balances_sums_sol_and_tokens(self) -> None:
        rows = asyncio.run(self.connector.fetch_balances())
        by_symbol = {r["symbol"]: r["quantity"] for r in rows}
        self.assertEqual(by_symbol["SOL"], 1.0)
        self.assertEqual(by_symbol["PUMP"], 5.0)
        self.assertEqual(by_symbol["USDC"], 10.0)
        self.assertEqual(self.connector._mint_by_symbol["PUMP"], PUMP_MINT)

    def test_fetch_prices_maps_mint_usd_to_symbol(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        prices = asyncio.run(self.connector.fetch_prices(["SOL", "PUMP", "USDC"]))
        self.assertEqual(prices["SOL"], 100.0)
        self.assertEqual(prices["PUMP"], 0.05)
        self.assertEqual(prices["USDC"], 1.0)

    def test_fetch_orders_sync_normalizes_buy_and_sell(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        rows = self.connector.fetch_orders_sync("PUMP/USDC", since_ms=None)
        self.assertEqual(len(rows), 2)
        buy = next(r for r in rows if r["type"] == "buy")
        sell = next(r for r in rows if r["type"] == "sell")
        self.assertEqual(buy["external_order_id"], "tx-buy-1")
        self.assertEqual(buy["quantity"], 4000.0)
        # 2 SOL * $100 / 4000 tokens = $0.05
        self.assertAlmostEqual(buy["price"], 0.05)
        self.assertEqual(sell["external_order_id"], "tx-sell-1")
        self.assertEqual(sell["quantity"], 100.0)
        self.assertAlmostEqual(sell["price"], 0.05)
        self.assertIsInstance(buy["executed_at"], datetime)

    def test_fetch_orders_sync_respects_since_ms(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        # After the buy fill, only the sell remains.
        since = int(
            datetime(2024, 7, 21, 12, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        rows = self.connector.fetch_orders_sync("PUMP/USDT", since_ms=since)
        self.assertEqual([r["external_order_id"] for r in rows], ["tx-sell-1"])

    def test_price_history_uses_coingecko_contract_chart(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        points = self.connector.fetch_price_history_sync(
            "PUMP/USDT",
            since_ms=0,
            days=7,
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["close"], 0.04)
        self.assertEqual(points[1]["price"], 0.045)
        chart_calls = [c for c in self.http.calls if "market_chart" in c[1]]
        self.assertEqual(len(chart_calls), 1)
        self.assertIn(PUMP_MINT, chart_calls[0][1])

    def test_balances_failure_raises(self) -> None:
        def boom(*_a, **_k):
            raise ConnectorFetchError("down")

        with patch.object(self.connector, "_request_json", side_effect=boom):
            with self.assertRaises(ConnectorFetchError):
                asyncio.run(self.connector.fetch_balances())


if __name__ == "__main__":
    unittest.main()
