"""Solana connector parsing and order-sync window. Uses no network and no portfolio.db."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.connectors.solana import (
    QUOTE_MINTS,
    USDC_MINT,
    USDT_MINT,
    WSOL_MINT,
    SolanaConnector,
)
from src.models.database import Asset, Base, Order, Position, migrate_position_token_address
from src.services.assets import AssetsService
from src.services.orders import QUOTE_CURRENCIES, OrderService
from src.utils.data_quality import ConnectorFetchError

WALLET = "Wallet111111111111111111111111111111111111111"
BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
WIF_MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
HOST = "https://mainnet.helius-rpc.com"
KEY = "test-helius-key"


def _config() -> Dict[str, str]:
    return {"hostname": HOST, "address": WALLET, "api_key": KEY}


def _fungible(mint: str, symbol: str, raw_balance: int, decimals: int = 6) -> Dict[str, Any]:
    return {
        "interface": "FungibleToken",
        "id": mint,
        "content": {"metadata": {"symbol": symbol, "name": symbol}},
        "token_info": {
            "symbol": symbol,
            "balance": raw_balance,
            "decimals": decimals,
            "price_info": {"price_per_token": 999, "currency": "USDC"},
        },
    }


def _assets_result(items: List[Dict[str, Any]], lamports: int = 0) -> Dict[str, Any]:
    return {
        "items": items,
        "nativeBalance": {"lamports": lamports, "price_per_sol": 150, "total_price": 1},
    }


def _token_balance(mint: str, amount: str) -> Dict[str, Any]:
    return {
        "mint": mint,
        "owner": WALLET,
        "uiTokenAmount": {"uiAmountString": amount, "decimals": 6, "amount": "0"},
    }


def _tx(
    signature: str,
    block_time: int,
    *,
    sol_pre: int = 1_000_000_000,
    sol_post: int = 1_000_000_000,
    fee: int = 5_000,
    pre: Optional[List[Dict[str, Any]]] = None,
    post: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    # Fee payer is the wallet. post already includes the fee unless the test
    # sets sol_post to the economic balance minus the fee.
    return {
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": [{"pubkey": WALLET, "signer": True}]},
        },
        "meta": {
            "err": None,
            "fee": fee,
            "preBalances": [sol_pre],
            "postBalances": [sol_post],
            "preTokenBalances": pre or [],
            "postTokenBalances": post or [],
        },
    }


class SolanaConnectorTests(unittest.TestCase):
    def test_quote_mints_match_exchange_quotes(self) -> None:
        self.assertEqual(set(QUOTE_MINTS.values()), set(QUOTE_CURRENCIES))

    def test_endpoint_appends_api_key_once(self) -> None:
        connector = SolanaConnector(_config())
        self.assertEqual(
            connector._endpoint(),
            "https://mainnet.helius-rpc.com?api-key=test-helius-key",
        )
        already = SolanaConnector(
            {**_config(), "hostname": "https://mainnet.helius-rpc.com/?api-key=existing"}
        )
        self.assertEqual(
            already._endpoint(),
            "https://mainnet.helius-rpc.com/?api-key=existing",
        )

    def test_balances_merge_sol_skip_nft_and_price_and_paginate(self) -> None:
        calls: List[Any] = []

        def transport(method: str, params: Any) -> Any:
            calls.append((method, params))
            if method != "getAssetsByOwner":
                raise AssertionError(method)
            page = params["page"]
            self.assertTrue(params["options"]["showFungible"])
            self.assertTrue(params["options"]["showNativeBalance"])
            self.assertFalse(params["options"]["showZeroBalance"])
            if page == 1:
                return _assets_result(
                    [
                        _fungible(BONK_MINT, "BONK", 2_500_000),
                        _fungible(WSOL_MINT, "SOL", 500_000_000, decimals=9),
                        {
                            "interface": "V1_NFT",
                            "id": "nft-mint",
                            "token_info": {"balance": 1, "decimals": 0, "symbol": "NFT"},
                        },
                    ],
                    lamports=1_000_000_000,
                )
            if page == 2:
                return _assets_result([_fungible(USDC_MINT, "USDC", 3_000_000)], lamports=0)
            return _assets_result([])

        connector = SolanaConnector(_config(), transport=transport)
        with unittest.mock.patch("src.connectors.solana.ASSET_PAGE_LIMIT", 3):
            rows = connector._fetch_balances_sync()
        by_symbol = {row["symbol"]: row["quantity"] for row in rows}
        self.assertEqual(by_symbol["SOL"], 1.5)
        self.assertEqual(by_symbol["BONK"], 2.5)
        self.assertEqual(by_symbol["USDC"], 3.0)
        by_address = {row["symbol"]: row["token_address"] for row in rows}
        self.assertEqual(by_address["SOL"], WSOL_MINT)
        self.assertEqual(by_address["BONK"], BONK_MINT)
        self.assertEqual(by_address["USDC"], USDC_MINT)
        self.assertTrue(all("_mint" not in row for row in rows))
        self.assertNotIn("NFT", by_symbol)
        self.assertTrue(all(row["exchange"] == "solana" for row in rows))
        self.assertEqual([params["page"] for method, params in calls], [1, 2])
        self.assertEqual(connector._symbols_by_mint[BONK_MINT], "BONK")

    def test_duplicate_symbols_get_a_mint_suffix(self) -> None:
        other = BONK_MINT[:-4] + "ZZZZ"

        def transport(method: str, params: Any) -> Any:
            if params["page"] > 1:
                return _assets_result([])
            return _assets_result(
                [
                    _fungible(BONK_MINT, "BONK", 1_000_000),
                    _fungible(other, "BONK", 2_000_000),
                ]
            )

        rows = SolanaConnector(_config(), transport=transport)._fetch_balances_sync()
        symbols = sorted(row["symbol"] for row in rows)
        self.assertEqual(len(symbols), 2)
        self.assertTrue(all(symbol.startswith("BONK.") for symbol in symbols))
        self.assertNotEqual(symbols[0], symbols[1])
        self.assertEqual({row["token_address"] for row in rows}, {BONK_MINT, other})

    def test_rpc_error_raises_and_empty_owner_is_empty(self) -> None:
        def fail(method: str, params: Any) -> Any:
            raise ConnectorFetchError("solana getAssetsByOwner: nope")

        connector = SolanaConnector(_config(), transport=fail)
        with self.assertRaises(ConnectorFetchError):
            connector._fetch_balances_sync()

        def empty(method: str, params: Any) -> Any:
            return {"items": [], "nativeBalance": {"lamports": 0}}

        self.assertEqual(
            SolanaConnector(_config(), transport=empty)._fetch_balances_sync(),
            [],
        )

    def test_http_error_and_no_assets_message(self) -> None:
        class _Response:
            def __init__(self, body: Dict[str, Any]):
                self._body = body

            def raise_for_status(self) -> None:
                return None

            def json(self) -> Dict[str, Any]:
                return self._body

        bodies = iter(
            [
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32004, "message": "No assets found for the specified owner."},
                    "id": "1",
                },
                {"jsonrpc": "2.0", "error": {"message": "Rate limit exceeded"}, "id": "1"},
            ]
        )

        def post(url: str, json: Dict[str, Any], timeout: float) -> _Response:
            self.assertIn("api-key=test-helius-key", url)
            return _Response(next(bodies))

        with unittest.mock.patch("src.connectors.solana.httpx.post", post):
            connector = SolanaConnector(_config())
            self.assertEqual(connector._fetch_balances_sync(), [])
            with self.assertRaises(ConnectorFetchError) as ctx:
                connector._fetch_balances_sync()
        self.assertNotIn(KEY, str(ctx.exception))

    def test_conversions_price_direction_and_ignores(self) -> None:
        now = 1_700_000_000
        signature = "sig" * 30  # longer than the old 64-char column

        def transport(method: str, params: Any) -> Any:
            if method == "getAssetsByOwner":
                if params["page"] > 1:
                    return _assets_result([])
                return _assets_result(
                    [
                        _fungible(BONK_MINT, "BONK", 5_000_000),
                        _fungible(WIF_MINT, "WIF", 1_000_000),
                    ]
                )
            data = [
                _tx(
                    signature + "sell",
                    now,
                    sol_pre=2_000_000_000,
                    sol_post=2_000_000_000 - 5_000,
                    pre=[_token_balance(BONK_MINT, "5"), _token_balance(USDT_MINT, "0")],
                    post=[_token_balance(BONK_MINT, "3"), _token_balance(USDT_MINT, "10")],
                ),
                _tx(
                    signature + "buy",
                    now - 10,
                    sol_pre=2_000_000_000,
                    sol_post=2_000_000_000 - 5_000 - 2_000_000,
                    pre=[_token_balance(BONK_MINT, "3"), _token_balance(USDC_MINT, "20")],
                    post=[_token_balance(BONK_MINT, "4"), _token_balance(USDC_MINT, "5")],
                ),
                _tx(
                    signature + "airdrop",
                    now - 20,
                    sol_pre=2_000_000_000,
                    sol_post=2_000_000_000 - 5_000,
                    pre=[_token_balance(BONK_MINT, "4")],
                    post=[_token_balance(BONK_MINT, "9")],
                ),
                _tx(
                    signature + "swap",
                    now - 30,
                    sol_pre=2_000_000_000,
                    sol_post=2_000_000_000 - 5_000,
                    pre=[_token_balance(BONK_MINT, "9"), _token_balance(WIF_MINT, "1")],
                    post=[_token_balance(BONK_MINT, "8"), _token_balance(WIF_MINT, "2")],
                ),
                _tx(
                    signature + "stables",
                    now - 40,
                    sol_pre=2_000_000_000,
                    sol_post=2_000_000_000 - 5_000,
                    pre=[_token_balance(USDT_MINT, "10"), _token_balance(USDC_MINT, "0")],
                    post=[_token_balance(USDT_MINT, "0"), _token_balance(USDC_MINT, "10")],
                ),
                _tx(
                    signature + "sol",
                    now - 50,
                    sol_pre=2_000_000_000,
                    sol_post=1_500_000_000 - 5_000,
                    pre=[_token_balance(USDC_MINT, "0")],
                    post=[_token_balance(USDC_MINT, "75")],
                ),
            ]
            return {"data": data, "paginationToken": None}

        connector = SolanaConnector(_config(), transport=transport)
        rows = connector.fetch_orders_sync("", None, paginate=True)
        by_id = {row["external_order_id"]: row for row in rows}
        sell = by_id[f"{signature}sell:BONK"]
        self.assertEqual(sell["type"], "sell")
        self.assertEqual(sell["quantity"], 2.0)
        self.assertEqual(sell["price"], 5.0)
        self.assertEqual(sell["exchange"], "solana")
        buy = by_id[f"{signature}buy:BONK"]
        self.assertEqual(buy["type"], "buy")
        self.assertEqual(buy["quantity"], 1.0)
        self.assertEqual(buy["price"], 15.0)
        sol = by_id[f"{signature}sol:SOL"]
        self.assertEqual(sol["type"], "sell")
        self.assertEqual(sol["quantity"], 0.5)
        self.assertEqual(sol["price"], 150.0)
        self.assertEqual(len(rows), 3)
        self.assertGreater(len(sell["external_order_id"]), 64)

    def test_pagination_stops_on_block_time_and_caches_history(self) -> None:
        calls: List[str] = []

        def transport(method: str, params: Any) -> Any:
            calls.append(method)
            if method == "getAssetsByOwner":
                if params["page"] > 1:
                    return _assets_result([])
                return _assets_result(
                    [
                        _fungible(BONK_MINT, "BONK", 1_000_000),
                        _fungible(WIF_MINT, "WIF", 1_000_000),
                    ]
                )
            config = params[1]
            if config.get("paginationToken") == "next":
                return {
                    "data": [
                        _tx(
                            "page2",
                            1_000,
                            pre=[_token_balance(WIF_MINT, "2"), _token_balance(USDT_MINT, "0")],
                            post=[_token_balance(WIF_MINT, "1"), _token_balance(USDT_MINT, "4")],
                        )
                    ],
                    "paginationToken": None,
                }
            return {
                "data": [
                    _tx(
                        "page1",
                        5_000,
                        pre=[_token_balance(BONK_MINT, "2"), _token_balance(USDC_MINT, "0")],
                        post=[_token_balance(BONK_MINT, "1"), _token_balance(USDC_MINT, "3")],
                    ),
                    _tx(
                        "too-old",
                        100,
                        pre=[_token_balance(BONK_MINT, "1"), _token_balance(USDC_MINT, "3")],
                        post=[_token_balance(BONK_MINT, "0"), _token_balance(USDC_MINT, "6")],
                    ),
                ],
                "paginationToken": "next",
            }

        connector = SolanaConnector(_config(), transport=transport)
        # 2_000 seconds → the 1_000s page is inside the window, 100s is not.
        bonk = connector.fetch_orders_sync("BONK/USDT", 2_000_000, paginate=True)
        wif = connector.fetch_orders_sync("WIF", 2_000_000, paginate=True)
        self.assertEqual(len(bonk), 1)
        self.assertEqual(bonk[0]["price"], 3.0)
        self.assertEqual(len(wif), 0)
        self.assertEqual(calls.count("getTransactionsForAddress"), 1)
        self.assertEqual(
            connector.fetch_orders_sync("WIF", None, paginate=True)[0]["type"],
            "sell",
        )
        self.assertGreater(calls.count("getTransactionsForAddress"), 1)

    def test_connection_requires_a_live_rpc(self) -> None:
        import asyncio

        missing = SolanaConnector({"hostname": HOST, "address": WALLET})
        self.assertFalse(asyncio.run(missing.test_connection()))

        def transport(method: str, params: Any) -> Any:
            self.assertEqual(method, "getAssetsByOwner")
            self.assertEqual(params["limit"], 1)
            return _assets_result([])

        ok = SolanaConnector(_config(), transport=transport)
        self.assertTrue(asyncio.run(ok.test_connection()))


class _BalanceConnector:
    def __init__(self, rows: List[Dict[str, Any]]):
        self.name = "solana"
        self.rows = rows

    async def fetch_balances(self) -> List[Dict[str, Any]]:
        return self.rows

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        return {}


class PositionTokenAddressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_sync_saves_mint_and_does_not_clear_it(self) -> None:
        connector = _BalanceConnector(
            [
                {
                    "symbol": "BONK",
                    "quantity": 2.0,
                    "exchange": "solana",
                    "token_address": BONK_MINT,
                }
            ]
        )
        asyncio.run(AssetsService(self.db).sync_from_connector(connector))
        position = self.db.query(Position).filter_by(symbol="BONK", exchange="solana").one()
        self.assertEqual(position.token_address, BONK_MINT)

        connector.rows = [{"symbol": "BONK", "quantity": 4.0, "exchange": "solana"}]
        asyncio.run(AssetsService(self.db).sync_from_connector(connector))
        self.db.refresh(position)
        self.assertEqual(position.quantity, 4.0)
        self.assertEqual(position.token_address, BONK_MINT)

    def test_exchange_balance_leaves_address_empty(self) -> None:
        connector = _BalanceConnector(
            [{"symbol": "BTC", "quantity": 1.0, "exchange": "solana"}]
        )
        connector.name = "binance"
        asyncio.run(AssetsService(self.db).sync_from_connector(connector))
        position = self.db.query(Position).one()
        self.assertIsNone(position.token_address)

    def test_migration_adds_column_and_keeps_rows(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        engine = create_engine(f"sqlite:///{path}")
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol VARCHAR(20), quantity FLOAT)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO positions (symbol, quantity) VALUES ('SOL', 1.5)"
                )
            migrate_position_token_address(bind=engine)
            migrate_position_token_address(bind=engine)
            with engine.connect() as conn:
                cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(positions)")}
                stored = conn.exec_driver_sql(
                    "SELECT symbol, quantity, token_address FROM positions"
                ).one()
            self.assertIn("token_address", cols)
            self.assertEqual(tuple(stored), ("SOL", 1.5, None))
        finally:
            engine.dispose()
            path.unlink(missing_ok=True)


class _Recording:
    def __init__(self, name: str, *, per_pair: bool, full_history: bool):
        self.name = name
        self._per_pair = per_pair
        self._full_history = full_history
        self.calls: List[Any] = []

    def syncs_per_market_pair(self) -> bool:
        return self._per_pair

    def full_history_when_empty(self) -> bool:
        return self._full_history

    def fetch_orders_sync(self, market_pair: str, since_ms: Optional[int], *, limit: int = 500, paginate: bool = False):
        self.calls.append((market_pair, since_ms, paginate))
        return []


class OrderSyncWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.svc = OrderService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _open(self, symbol: str, exchange: str) -> Position:
        asset = Asset(symbol=symbol, name=symbol)
        self.db.add(asset)
        self.db.flush()
        position = Position(
            asset_id=asset.id,
            symbol=symbol,
            quantity=1,
            first_bought_at=datetime.utcnow(),
            exchange=exchange,
            status="open",
            source="synced",
        )
        self.db.add(position)
        self.db.commit()
        return position

    def test_exchange_window_stays_recent_and_per_pair(self) -> None:
        self._open("BTC", "binance")
        connector = _Recording("binance", per_pair=True, full_history=False)
        before = datetime.utcnow()
        added = self.svc.sync_orders_from_connector(connector, "BTC")
        after = datetime.utcnow()
        self.assertEqual(added, 0)
        self.assertEqual([call[0] for call in connector.calls], ["BTC/USDT", "BTC/USDC"])
        self.assertTrue(all(call[2] is False for call in connector.calls))
        low = int((before - timedelta(hours=2, seconds=2)).timestamp() * 1000)
        high = int((after - timedelta(hours=2) + timedelta(seconds=2)).timestamp() * 1000)
        self.assertTrue(all(low <= call[1] <= high for call in connector.calls))

    def test_solana_cold_start_then_overlap(self) -> None:
        position = self._open("BONK", "solana")
        connector = _Recording("solana", per_pair=False, full_history=True)
        self.svc.sync_orders_from_connector(connector, "BONK")
        self.assertEqual(connector.calls, [("BONK", None, True)])

        executed = datetime.utcnow() - timedelta(days=4)
        self.db.add(
            Order(
                position_id=position.id,
                symbol="BONK",
                type="buy",
                quantity=1,
                price=2,
                executed_at=executed,
                exchange="solana",
                external_order_id="already",
            )
        )
        self.db.commit()
        connector.calls.clear()
        self.svc.sync_orders_from_connector(connector, "BONK")
        self.assertEqual(len(connector.calls), 1)
        market_pair, since_ms, paginate = connector.calls[0]
        self.assertEqual(market_pair, "BONK")
        self.assertTrue(paginate)
        expected = int((executed - timedelta(hours=2)).timestamp() * 1000)
        self.assertAlmostEqual(since_ms, expected, delta=2000)


if __name__ == "__main__":
    unittest.main()
