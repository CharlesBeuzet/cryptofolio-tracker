"""Mobula balances, swap legs, manual buys, and on-chain charts. Isolated SQLite only."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.connectors.mobula import MobulaConnector
from src.models.database import (
    Asset,
    Base,
    Order,
    Position,
    migrate_positions_token_address,
)
from src.services.analyzer import PositionAnalyzerService
from src.services.assets import AssetsService
from src.services.mobula_client import (
    NATIVE_PLACEHOLDER,
    WRAPPED_NATIVE,
    MobulaClient,
    chart_address,
    orders_from_transaction,
    portfolio_params,
    portfolio_rows,
)
from src.services.onchain_orders import OnchainOrderService, unpriced_quantity
from src.services.orders import OrderService
from src.services.price_history import PriceHistoryService, _cache
from src.utils.data_quality import ConnectorFetchError

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BONK_A = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
BONK_B = "BonkMintXXXXXXXXXXXXXXXXXXXXXXXXXXXX2222"


def _portfolio_payload():
    return {
        "data": {
            "assets": [
                {
                    "asset": {"symbol": "BONK", "name": "Bonk"},
                    "price": 0.02,
                    "contracts_balances": [
                        {"address": BONK_A, "balance": 100, "chainId": "solana:solana"},
                        {"address": BONK_A, "balance": 25, "chainId": "solana:solana"},
                        {"address": BONK_B, "balance": 5, "chainId": "solana:solana"},
                    ],
                },
                {
                    "symbol": "ETH",
                    "name": "Ether",
                    "price": 3000,
                    "contracts_balances": [
                        {
                            "address": NATIVE_PLACEHOLDER,
                            "balance": 1.5,
                            "chainId": "evm:1",
                        }
                    ],
                },
                {
                    "symbol": "GHOST",
                    "contracts_balances": [
                        {
                            "address": "0xabc",
                            "balance": 1,
                            "chainId": "evm:250",
                        }
                    ],
                },
            ]
        }
    }


class MobulaParseTests(unittest.TestCase):
    def test_portfolio_params_skip_expensive_flags(self) -> None:
        params = portfolio_params(["wallet-a", "wallet-b"], ["solana", "ethereum"])
        self.assertNotIn("fetchAllChains", params)
        self.assertNotIn("backfillTransfers", params)
        self.assertEqual(params["cache"], "true")
        self.assertEqual(params["stale"], "3600")
        self.assertEqual(params["minliq"], "0")
        self.assertEqual(params["blockchains"], "solana,ethereum")

    def test_portfolio_rows_sum_disambiguate_and_map_chains(self) -> None:
        rows = portfolio_rows(_portfolio_payload(), ["solana", "ethereum"])
        by_token = {row["token_address"]: row for row in rows}
        self.assertEqual(set(by_token), {BONK_A, BONK_B, NATIVE_PLACEHOLDER})
        self.assertAlmostEqual(by_token[BONK_A]["quantity"], 125)
        self.assertEqual(by_token[BONK_A]["exchange"], "solana")
        self.assertEqual(by_token[BONK_B]["symbol"], "BONK")
        self.assertEqual(by_token[BONK_A]["symbol"], "BONK-B263")
        self.assertEqual(by_token[NATIVE_PLACEHOLDER]["exchange"], "ethereum")
        self.assertAlmostEqual(by_token[NATIVE_PLACEHOLDER]["price"], 3000)

    def test_assets_without_contracts_are_rejected(self) -> None:
        with self.assertRaises(ConnectorFetchError):
            portfolio_rows({"data": {"assets": [{"symbol": "SOL", "price": 1}]}}, ["solana"])

    def test_swap_prices_use_the_stable_leg(self) -> None:
        rows = orders_from_transaction(
            {
                "chainId": "solana:solana",
                "txHash": "sig123",
                "txDateMs": 1_700_000_000_000,
                "actions": [
                    {
                        "model": "swap",
                        "swapAmountIn": 1000,
                        "swapAmountOut": 25,
                        "swapAmountUsd": 999,
                        "swapAssetIn": {"symbol": "BONK", "contract": BONK_A, "name": "Bonk"},
                        "swapAssetOut": {"symbol": "USDC", "contract": USDC, "name": "USD Coin"},
                    },
                    {
                        "model": "transfer",
                        "transferType": "VAULT_DEPOSIT",
                        "transferAmount": 10,
                    },
                ],
            }
        )
        self.assertEqual(len(rows), 2)
        buy = next(row for row in rows if row["type"] == "buy")
        sell = next(row for row in rows if row["type"] == "sell")
        self.assertEqual(buy["symbol"], "BONK")
        self.assertAlmostEqual(buy["price"], 0.025)
        self.assertEqual(buy["exchange"], "solana")
        self.assertEqual(buy["external_order_id"], f"sig123:buy:{BONK_A}")
        self.assertEqual(sell["symbol"], "USDC")
        self.assertAlmostEqual(sell["price"], 1.0)
        self.assertEqual(sell["external_order_id"], f"sig123:sell:{USDC}")

    def test_swap_without_a_notional_is_skipped(self) -> None:
        rows = orders_from_transaction(
            {
                "chainId": "evm:8453",
                "txHash": "0xabc",
                "txDateMs": 1_700_000_000_000,
                "actions": [
                    {
                        "model": "swap",
                        "swapAmountIn": 2,
                        "swapAmountOut": 3,
                        "swapAmountUsd": 0,
                        "swapAssetIn": {"symbol": "AAA", "contract": "0x111"},
                        "swapAssetOut": {"symbol": "BBB", "contract": "0x222"},
                    }
                ],
            }
        )
        self.assertEqual(rows, [])

    def test_usd_notional_prices_both_legs(self) -> None:
        rows = orders_from_transaction(
            {
                "chainId": "base",
                "txHash": "0xdef",
                "txDateMs": 1_700_000_000_000,
                "actions": [
                    {
                        "model": "swap",
                        "swapAmountIn": 2,
                        "swapAmountOut": 4,
                        "swapAmountUsd": 20,
                        "swapAssetIn": {"symbol": "AAA", "contract": "0x111"},
                        "swapAssetOut": {"symbol": "BBB", "contract": "0x222"},
                    }
                ],
            }
        )
        prices = {row["symbol"]: row["price"] for row in rows}
        self.assertAlmostEqual(prices["AAA"], 10)
        self.assertAlmostEqual(prices["BBB"], 5)
        self.assertEqual(rows[0]["exchange"], "base")

    def test_native_chart_uses_wrapped_token(self) -> None:
        self.assertEqual(
            chart_address("ethereum", NATIVE_PLACEHOLDER),
            WRAPPED_NATIVE["ethereum"].lower(),
        )
        self.assertEqual(
            chart_address("solana", BONK_A),
            BONK_A,
        )


class MobulaClientTests(unittest.TestCase):
    def _client(self, handler, sleeper=None, clock=None):
        http = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.mobula.io",
        )
        kwargs = {"http": http, "min_interval": 1.05}
        if sleeper:
            kwargs["sleeper"] = sleeper
        if clock:
            kwargs["clock"] = clock
        return MobulaClient("test-key", **kwargs)

    def test_portfolio_request_is_throttled_and_scoped(self) -> None:
        seen = []
        clock = {"now": 10.0}
        slept = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            self.assertEqual(request.headers["Authorization"], "test-key")
            return httpx.Response(200, json={"data": {"assets": []}})

        def sleeper(wait: float) -> None:
            slept.append(wait)
            clock["now"] += wait

        client = self._client(handler, sleeper=sleeper, clock=lambda: clock["now"])
        client.portfolio(["wallet-a"], ["solana"])
        client.portfolio(["wallet-a"], ["solana"])
        self.assertEqual(len(seen), 2)
        self.assertTrue(slept)
        self.assertGreaterEqual(slept[0], 1)
        self.assertNotIn("fetchAllChains", seen[0])
        self.assertNotIn("backfillTransfers", seen[0])
        self.assertIn("blockchains=solana", seen[0])

    def test_http_error_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(451, json={"error": "blocked"})

        client = self._client(handler, sleeper=lambda _wait: None, clock=lambda: 0.0)
        with self.assertRaises(ConnectorFetchError):
            client.portfolio(["wallet-a"], ["solana"])


class _MemoryDb(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()


class ChainSyncTests(_MemoryDb):
    def test_chain_positions_close_only_the_synced_slug(self) -> None:
        asset = Asset(symbol="OLD", name="Old", current_price=1)
        kept = Asset(symbol="BTC", name="Bitcoin", current_price=10)
        self.db.add_all(
            [
                asset,
                kept,
                Position(
                    asset=asset,
                    symbol="OLD",
                    quantity=3,
                    first_bought_at=datetime(2024, 1, 1),
                    exchange="solana",
                    status="open",
                    source="synced",
                    token_address="old-mint",
                ),
                Position(
                    asset=kept,
                    symbol="BTC",
                    quantity=1,
                    first_bought_at=datetime(2024, 1, 1),
                    exchange="binance",
                    status="open",
                    source="synced",
                ),
            ]
        )
        self.db.commit()

        class Connector:
            name = "mobula"
            chain_scoped = True

            def configured_chains(self):
                return ["solana"]

            async def fetch_balances(self):
                return [
                    {
                        "symbol": "BONK",
                        "quantity": 10,
                        "exchange": "solana",
                        "token_address": BONK_A,
                        "price": 0.02,
                    }
                ]

            async def fetch_prices(self, symbols):
                return {"BONK": 0.02}

        result = asyncio.run(AssetsService(self.db).sync_from_connector(Connector()))
        self.assertEqual(result["positions_closed"], 1)
        bonk = self.db.query(Position).filter(Position.symbol == "BONK").one()
        self.assertEqual(bonk.exchange, "solana")
        self.assertEqual(bonk.token_address, BONK_A)
        self.assertEqual(bonk.status, "open")
        self.assertAlmostEqual(bonk.asset.current_price, 0.02)
        old = self.db.query(Position).filter(Position.symbol == "OLD").one()
        self.assertEqual(old.status, "closed")
        btc = self.db.query(Position).filter(Position.symbol == "BTC").one()
        self.assertEqual(btc.status, "open")
        self.assertEqual(btc.quantity, 1)

    def test_failed_fetch_does_not_close(self) -> None:
        asset = Asset(symbol="BONK", name="Bonk")
        self.db.add(asset)
        self.db.add(
            Position(
                asset=asset,
                symbol="BONK",
                quantity=4,
                first_bought_at=datetime(2024, 1, 1),
                exchange="solana",
                status="open",
                source="synced",
                token_address=BONK_A,
            )
        )
        self.db.commit()

        class Connector:
            name = "mobula"
            chain_scoped = True

            def configured_chains(self):
                return ["solana"]

            async def fetch_balances(self):
                raise ConnectorFetchError("down")

            async def fetch_prices(self, symbols):
                return {}

        with self.assertRaises(ConnectorFetchError):
            asyncio.run(AssetsService(self.db).sync_from_connector(Connector()))
        position = self.db.query(Position).one()
        self.assertEqual(position.status, "open")
        self.assertEqual(position.quantity, 4)


class ActivityAndManualOrderTests(_MemoryDb):
    def test_activity_cursor_then_manual_cap_and_recompute(self) -> None:
        pages = [
            {
                "orders": [
                    {
                        "symbol": "BONK",
                        "name": "Bonk",
                        "token_address": BONK_A,
                        "type": "buy",
                        "quantity": 40,
                        "price": 0.02,
                        "executed_at": datetime(2024, 1, 2),
                        "exchange": "solana",
                        "external_order_id": f"sig:buy:{BONK_A}",
                    }
                ],
                "count": 100,
                "page_size": 100,
                "oldest_tx_ms": 1_000,
                "newest_tx_ms": 2_000,
            },
            {
                "orders": [],
                "count": 10,
                "page_size": 100,
                "oldest_tx_ms": 400,
                "newest_tx_ms": 900,
            },
            {
                "orders": [
                    {
                        "symbol": "BONK",
                        "name": "Bonk",
                        "token_address": BONK_A,
                        "type": "buy",
                        "quantity": 40,
                        "price": 0.02,
                        "executed_at": datetime(2024, 1, 2),
                        "exchange": "solana",
                        "external_order_id": f"sig:buy:{BONK_A}",
                    }
                ],
                "count": 1,
                "page_size": 100,
                "oldest_tx_ms": 2_100,
                "newest_tx_ms": 3_000,
            },
        ]
        calls = []

        class Connector:
            syncs_wallet_activity = True

            def wallets(self):
                return ["wallet-1"]

            def fetch_activity_page(self, wallet, from_ms=None, to_ms=None):
                calls.append({"wallet": wallet, "from": from_ms, "to": to_ms})
                return pages.pop(0)

        service = OrderService(self.db)
        added = service.sync_wallet_activity(Connector())
        self.assertEqual(added, 1)
        self.assertEqual(calls, [
            {"wallet": "wallet-1", "from": None, "to": None},
            {"wallet": "wallet-1", "from": None, "to": 999},
        ])
        added_again = service.sync_wallet_activity(Connector())
        self.assertEqual(added_again, 0)
        self.assertEqual(calls[-1]["from"], 2000)
        self.assertEqual(self.db.query(Order).count(), 1)

        position = self.db.query(Position).filter(Position.token_address == BONK_A).one()
        position.quantity = 100
        position.status = "open"
        position.asset.current_price = 0.05
        self.db.commit()
        PositionAnalyzerService(self.db).recompute_position(position.id, 0.05)
        self.assertAlmostEqual(unpriced_quantity(position), 60)

        onchain = OnchainOrderService(self.db)
        with self.assertRaises(ValueError):
            onchain.add_buy(position.id, 61, 0.03, datetime(2024, 1, 3))

        updated = onchain.add_buy(position.id, 60, 0.04, datetime(2024, 1, 3))
        self.assertAlmostEqual(updated.metrics.avg_entry_price, 0.032)
        self.assertAlmostEqual(updated.metrics.order_derived_qty, 100)
        self.assertAlmostEqual(unpriced_quantity(updated), 0)
        # Remaining 100 tokens marked at 0.05 against a 0.032 average.
        self.assertAlmostEqual(updated.metrics.unrealised_pnl, 1.8)

        manual = next(
            order for order in updated.orders if (order.external_order_id or "").startswith("manual:")
        )
        watermark = updated.metrics.last_processed_order_id
        self.assertEqual(watermark, max(order.id for order in updated.orders))
        again = PositionAnalyzerService(self.db).apply_new_orders(updated.id, 0.05)
        self.assertAlmostEqual(again.avg_entry_price, 0.032)
        self.assertAlmostEqual(again.order_derived_qty, 100)

        mobula_order = next(
            order for order in updated.orders if not (order.external_order_id or "").startswith("manual:")
        )
        with self.assertRaises(ValueError):
            onchain.delete_manual(mobula_order.id)

        deleted = onchain.delete_manual(manual.id)
        self.assertAlmostEqual(deleted.metrics.avg_entry_price, 0.02)
        self.assertAlmostEqual(deleted.metrics.order_derived_qty, 40)
        self.assertAlmostEqual(unpriced_quantity(deleted), 60)

    def test_backdated_manual_buy_replays_before_an_existing_sell(self) -> None:
        asset = Asset(symbol="BONK", name="Bonk", current_price=5)
        self.db.add(asset)
        self.db.flush()
        position = Position(
            asset_id=asset.id,
            symbol="BONK",
            quantity=10,
            first_bought_at=datetime(2024, 1, 1),
            exchange="solana",
            status="open",
            source="synced",
            token_address=BONK_A,
        )
        self.db.add(position)
        self.db.flush()
        self.db.add(
            Order(
                position_id=position.id,
                symbol="BONK",
                type="sell",
                quantity=4,
                price=6,
                executed_at=datetime(2024, 2, 1),
                exchange="solana",
                external_order_id="sig:sell:bonk",
            )
        )
        self.db.commit()
        PositionAnalyzerService(self.db).recompute_position(position.id, 5)
        self.assertAlmostEqual(position.metrics.realised_pnl, 0)

        updated = OnchainOrderService(self.db).add_buy(
            position.id,
            10,
            2,
            datetime(2024, 1, 1),
        )
        self.assertAlmostEqual(updated.metrics.realised_pnl, 16)
        self.assertAlmostEqual(updated.metrics.avg_entry_price, 2)
        self.assertAlmostEqual(updated.metrics.order_derived_qty, 6)
        self.assertAlmostEqual(updated.metrics.unrealised_pnl, 18)


class PriceHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        _cache.clear()

    def test_ohlcv_uses_the_contract_on_the_chain_slug(self) -> None:
        calls = []

        class Client:
            def ohlcv(self, address, chain, *, period, amount, from_ms):
                calls.append(
                    {"address": address, "chain": chain, "period": period, "amount": amount}
                )
                return {
                    "data": [
                        {"time": 1_700_000_000_000, "open": 1, "high": 2, "low": 0.5, "close": 1.5}
                    ]
                }

        service = PriceHistoryService(client=Client(), chain_slugs=["ethereum", "solana"])
        result = asyncio.run(
            service.fetch("ETH", 7, "ethereum", token_address=NATIVE_PLACEHOLDER)
        )
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(calls[0]["address"], WRAPPED_NATIVE["ethereum"].lower())
        self.assertEqual(calls[0]["chain"], "ethereum")
        self.assertEqual(calls[0]["period"], "1h")
        self.assertAlmostEqual(result.points[0]["close"], 1.5)
        asyncio.run(service.fetch("ETH", 7, "ethereum", token_address=NATIVE_PLACEHOLDER))
        self.assertEqual(len(calls), 1)


class MigrationTests(unittest.TestCase):
    def test_token_address_column_is_additive(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol VARCHAR(20), quantity FLOAT)"
            )
            conn.exec_driver_sql(
                "INSERT INTO positions (symbol, quantity) VALUES ('BTC', 1)"
            )
        migrate_positions_token_address(bind=engine)
        migrate_positions_token_address(bind=engine)
        with engine.begin() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(positions)")]
            qty = conn.exec_driver_sql("SELECT quantity FROM positions").scalar()
        self.assertIn("token_address", cols)
        self.assertNotIn("chain", cols)
        self.assertEqual(qty, 1)
        engine.dispose()


class ConnectorLocalTests(unittest.TestCase):
    def test_connection_check_does_not_call_mobula(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("network")

        http = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.mobula.io",
        )
        client = MobulaClient("real-key", http=http, min_interval=0)
        ready = MobulaConnector(
            {
                "api_key": "real-key",
                "wallets": ["wallet-a"],
                "blockchains": ["solana", "evm:1"],
            },
            client=client,
        )
        missing = MobulaConnector({"api_key": "YOUR_MOBULA_API_KEY", "wallets": [], "blockchains": []})
        self.assertTrue(asyncio.run(ready.test_connection()))
        self.assertEqual(ready.configured_chains(), ["solana", "ethereum"])
        self.assertFalse(asyncio.run(missing.test_connection()))
        self.assertEqual(asyncio.run(ready.fetch_orders()), [])


if __name__ == "__main__":
    unittest.main()
