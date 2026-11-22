"""Zerion EVM connector unit tests (mocked HTTP — no live APIs / portfolio.db)."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from src.connectors.zerion import ZerionConnector
from src.utils.data_quality import ConnectorFetchError

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"


class _FakeHttp:
    """Route ZerionConnector._request_json calls to canned payloads."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
        self.positions: Dict[str, Any] = {
            "data": [
                {
                    "type": "positions",
                    "id": "eth-wallet",
                    "attributes": {
                        "position_type": "wallet",
                        "quantity": {"float": 1.5, "numeric": "1.5"},
                        "price": 2500.0,
                        "value": 3750.0,
                        "fungible_info": {
                            "symbol": "ETH",
                            "name": "Ethereum",
                            "implementations": [
                                {
                                    "chain_id": "ethereum",
                                    "address": "",
                                    "decimals": 18,
                                }
                            ],
                        },
                    },
                    "relationships": {
                        "chain": {"data": {"type": "chains", "id": "ethereum"}},
                        "fungible": {"data": {"type": "fungibles", "id": "eth"}},
                    },
                },
                {
                    "type": "positions",
                    "id": "uni-wallet",
                    "attributes": {
                        "position_type": "wallet",
                        "quantity": {"float": 10.0, "numeric": "10"},
                        "price": 8.0,
                        "value": 80.0,
                        "fungible_info": {
                            "symbol": "UNI",
                            "name": "Uniswap",
                            "implementations": [
                                {
                                    "chain_id": "ethereum",
                                    "address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                                    "decimals": 18,
                                }
                            ],
                        },
                    },
                    "relationships": {
                        "chain": {"data": {"type": "chains", "id": "ethereum"}},
                        "fungible": {"data": {"type": "fungibles", "id": "uni"}},
                    },
                },
                {
                    "type": "positions",
                    "id": "usdc-wallet",
                    "attributes": {
                        "position_type": "wallet",
                        "quantity": {"float": 100.0, "numeric": "100"},
                        "price": 1.0,
                        "value": 100.0,
                        "fungible_info": {
                            "symbol": "USDC",
                            "name": "USD Coin",
                            "implementations": [
                                {
                                    "chain_id": "base",
                                    "address": USDC,
                                    "decimals": 6,
                                }
                            ],
                        },
                    },
                    "relationships": {
                        "chain": {"data": {"type": "chains", "id": "base"}},
                        "fungible": {"data": {"type": "fungibles", "id": "usd-coin"}},
                    },
                },
            ]
        }
        self.transactions: Dict[str, Any] = {
            "data": [
                {
                    "type": "transactions",
                    "id": "0xbuy1",
                    "attributes": {
                        "operation_type": "trade",
                        "hash": "0xbuy1",
                        "mined_at": "2024-07-21T03:07:19Z",
                        "transfers": [
                            {
                                "direction": "out",
                                "quantity": {"float": 0.1},
                                "value": 250.0,
                                "price": 2500.0,
                                "fungible_info": {
                                    "symbol": "ETH",
                                    "implementations": [
                                        {"chain_id": "ethereum", "address": ""}
                                    ],
                                },
                            },
                            {
                                "direction": "in",
                                "quantity": {"float": 40.0},
                                "value": 240.0,
                                "price": 6.0,
                                "fungible_info": {
                                    "symbol": "UNI",
                                    "implementations": [
                                        {
                                            "chain_id": "ethereum",
                                            "address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                                        }
                                    ],
                                },
                            },
                        ],
                    },
                    "relationships": {
                        "chain": {"data": {"type": "chains", "id": "ethereum"}},
                    },
                },
                {
                    "type": "transactions",
                    "id": "0xsell1",
                    "attributes": {
                        "operation_type": "send",
                        "hash": "0xsell1",
                        "mined_at": "2024-07-22T01:00:00Z",
                        "transfers": [
                            {
                                "direction": "out",
                                "quantity": {"float": 5.0},
                                "value": 50.0,
                                "price": 10.0,
                                "fungible_info": {
                                    "symbol": "UNI",
                                    "implementations": [
                                        {
                                            "chain_id": "ethereum",
                                            "address": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                    "relationships": {
                        "chain": {"data": {"type": "chains", "id": "ethereum"}},
                    },
                },
            ],
            "links": {},
        }
        self.portfolio: Dict[str, Any] = {
            "data": {
                "type": "portfolio",
                "attributes": {"total": {"positions": 3930.0}},
            }
        }
        self.coingecko: Dict[str, Any] = {
            "prices": [
                [1_721_000_000_000, 6.0],
                [1_721_000_360_000, 6.5],
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
        absolute: bool = False,
    ) -> Any:
        self.calls.append((method, path, params))
        if "positions" in path:
            return self.positions
        if "transactions" in path:
            return self.transactions
        if "portfolio" in path:
            return self.portfolio
        if "market_chart" in path:
            return self.coingecko
        raise AssertionError(f"unexpected request {method} {path} params={params}")


class ZerionConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = ZerionConnector(
            {
                "address": "0x42b9df65b219b3dd36ff330a4dd8f327a6ada990",
                "hostname": "https://api.zerion.io",
                "api_key": "test-zerion-key",
                "chain_ids": "ethereum,base",
            }
        )
        self.http = _FakeHttp()
        self._patcher = patch.object(
            self.connector, "_request_json", side_effect=self.http
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def test_fetch_balances_aggregates_symbols(self) -> None:
        rows = asyncio.run(self.connector.fetch_balances())
        by_symbol = {r["symbol"]: r["quantity"] for r in rows}
        self.assertEqual(by_symbol["ETH"], 1.5)
        self.assertEqual(by_symbol["UNI"], 10.0)
        self.assertEqual(by_symbol["USDC"], 100.0)
        self.assertEqual(self.connector._impl_by_symbol["UNI"][0], "ethereum")
        pos_calls = [c for c in self.http.calls if "positions" in c[1]]
        self.assertEqual(len(pos_calls), 1)
        self.assertEqual(pos_calls[0][2]["filter[chain_ids]"], "ethereum,base")

    def test_fetch_prices_from_positions(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        prices = asyncio.run(self.connector.fetch_prices(["ETH", "UNI", "USDC"]))
        self.assertEqual(prices["ETH"], 2500.0)
        self.assertEqual(prices["UNI"], 8.0)
        self.assertEqual(prices["USDC"], 1.0)

    def test_fetch_orders_sync_from_transfers(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        rows = self.connector.fetch_orders_sync("UNI/USDC", since_ms=None)
        self.assertEqual(len(rows), 2)
        buy = next(r for r in rows if r["type"] == "buy")
        sell = next(r for r in rows if r["type"] == "sell")
        self.assertEqual(buy["external_order_id"], "0xbuy1:buy:UNI:1")
        self.assertEqual(buy["quantity"], 40.0)
        self.assertAlmostEqual(buy["price"], 6.0)
        self.assertEqual(sell["external_order_id"], "0xsell1:sell:UNI:0")
        self.assertEqual(sell["quantity"], 5.0)
        self.assertAlmostEqual(sell["price"], 10.0)
        self.assertIsInstance(buy["executed_at"], datetime)

    def test_fetch_orders_sync_respects_since_ms(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        since = int(
            datetime(2024, 7, 21, 12, 0, tzinfo=timezone.utc).timestamp() * 1000
        )
        rows = self.connector.fetch_orders_sync("UNI/USDT", since_ms=since)
        self.assertEqual([r["external_order_id"] for r in rows], ["0xsell1:sell:UNI:0"])

    def test_price_history_uses_coingecko_contract_chart(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        points = self.connector.fetch_price_history_sync(
            "UNI/USDT",
            since_ms=0,
            days=7,
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["close"], 6.0)
        self.assertEqual(points[1]["price"], 6.5)
        chart_calls = [c for c in self.http.calls if "market_chart" in c[1]]
        self.assertEqual(len(chart_calls), 1)
        self.assertIn("ethereum/contract/", chart_calls[0][1])
        self.assertIn("0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", chart_calls[0][1])

    def test_price_history_hydrates_impl_on_fresh_connector(self) -> None:
        """Charts construct a new connector — must load positions before CoinGecko."""
        fresh = ZerionConnector(
            {
                "address": "0x42b9df65b219b3dd36ff330a4dd8f327a6ada990",
                "hostname": "https://api.zerion.io",
                "api_key": "test-zerion-key",
            }
        )
        http = _FakeHttp()
        with patch.object(fresh, "_request_json", side_effect=http):
            points = fresh.fetch_price_history_sync("UNI/USDT", since_ms=0, days=7)
        self.assertEqual(len(points), 2)
        pos_calls = [c for c in http.calls if "positions" in c[1]]
        chart_calls = [c for c in http.calls if "market_chart" in c[1]]
        self.assertEqual(len(pos_calls), 1)
        self.assertEqual(len(chart_calls), 1)
        self.assertIn("0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", chart_calls[0][1])

    def test_price_history_long_range_uses_coingecko_max(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        self.connector.fetch_price_history_sync("UNI/USDT", since_ms=0, days=730)
        chart_calls = [c for c in self.http.calls if "market_chart" in c[1]]
        self.assertEqual(len(chart_calls), 1)
        self.assertEqual(chart_calls[0][2].get("days"), "max")

    def test_price_history_native_eth(self) -> None:
        asyncio.run(self.connector.fetch_balances())
        self.connector.fetch_price_history_sync("ETH/USDT", since_ms=0, days=1)
        chart_calls = [c for c in self.http.calls if "market_chart" in c[1]]
        self.assertTrue(any("coins/ethereum/market_chart" in c[1] for c in chart_calls))

    def test_balances_failure_raises(self) -> None:
        def boom(*_a, **_k):
            raise ConnectorFetchError("down")

        with patch.object(self.connector, "_request_json", side_effect=boom):
            with self.assertRaises(ConnectorFetchError):
                asyncio.run(self.connector.fetch_balances())

    def test_test_connection_uses_portfolio(self) -> None:
        ok = asyncio.run(self.connector.test_connection())
        self.assertTrue(ok)
        self.assertTrue(any("portfolio" in c[1] for c in self.http.calls))


if __name__ == "__main__":
    unittest.main()
