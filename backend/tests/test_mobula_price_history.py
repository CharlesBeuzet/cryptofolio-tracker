"""Mobula OHLCV client and on-chain price-history routing.

Uses httpx.MockTransport and temporary SQLite files. Never opens portfolio.db.
"""
from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import httpx

from src.services.mobula_client import (
    MAX_CANDLES_PER_REQUEST,
    MobulaClient,
    period_for_days,
)
from src.services.price_history import (
    NOT_FOUND,
    RESOLVED,
    PriceHistoryService,
    clear_price_history_cache,
    lookup_onchain_token_address,
)
from src.utils.data_quality import ConnectorFetchError


def _candle(ts_ms: int, close: float) -> Dict[str, Any]:
    return {
        "t": ts_ms,
        "o": close - 0.1,
        "h": close + 0.2,
        "l": close - 0.2,
        "c": close,
        "v": 10,
    }


class PeriodTests(unittest.TestCase):
    def test_period_matches_exchange_buckets(self) -> None:
        self.assertEqual(period_for_days(1), "1h")
        self.assertEqual(period_for_days(7), "4h")
        self.assertEqual(period_for_days(8), "12h")
        self.assertEqual(period_for_days(30), "12h")
        self.assertEqual(period_for_days(31), "1d")
        self.assertEqual(period_for_days(90), "1d")
        self.assertEqual(period_for_days(91), "1w")


class MobulaClientTests(unittest.TestCase):
    def test_missing_api_key_does_not_call_http(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request {request.url}")

        client = MobulaClient(api_key="", transport=httpx.MockTransport(handler))
        with self.assertRaises(ConnectorFetchError) as caught:
            client.fetch_ohlcv("mint", "solana", since_ms=0, days=1)
        self.assertIn("API key is not configured", str(caught.exception))

    def test_reads_api_key_from_mobula_section(self) -> None:
        seen: List[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["Authorization"])
            return httpx.Response(200, json={"data": [_candle(1_700_000_000_000, 2.0)]})

        with patch(
            "src.config.loader.get_section",
            return_value={"api_key": "from-config"},
        ):
            client = MobulaClient(transport=httpx.MockTransport(handler))
            points = client.fetch_ohlcv(
                "So11111111111111111111111111111111111111112",
                "solana",
                since_ms=0,
                days=1,
            )

        self.assertEqual(seen, ["from-config"])
        self.assertEqual(points[0]["close"], 2.0)
        self.assertEqual(points[0]["price"], 2.0)
        self.assertEqual(points[0]["timestamp"], datetime.fromtimestamp(1_700_000_000, tz=timezone.utc))

    def test_request_uses_exchange_as_chain_id(self) -> None:
        seen: List[Dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(request.url.params))
            return httpx.Response(
                200,
                json={"data": [_candle(1_700_000_000_000, 3.0)]},
            )

        client = MobulaClient(api_key="secret", transport=httpx.MockTransport(handler))
        client.fetch_ohlcv("0xabc", "ethereum", since_ms=0, days=40)

        self.assertEqual(seen[0]["chainId"], "ethereum")
        self.assertEqual(seen[0]["address"], "0xabc")
        self.assertEqual(seen[0]["period"], "1d")
        self.assertEqual(seen[0]["usd"], "true")
        self.assertEqual(seen[0]["fill"], "true")
        self.assertEqual(seen[0]["enableAssetHistory"], "true")

    def test_paginates_when_a_page_is_full(self) -> None:
        candles = [_candle(1_000 * (index + 1), 1.0 + index) for index in range(3)]
        calls: List[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.params["from"])
            amount = int(request.url.params["amount"])
            calls.append(start)
            batch = [row for row in candles if row["t"] >= start][:amount]
            return httpx.Response(200, json={"data": batch})

        client = MobulaClient(api_key="secret", transport=httpx.MockTransport(handler))
        with patch("src.services.mobula_client.MAX_CANDLES_PER_REQUEST", 2):
            points = client.fetch_ohlcv("mint", "solana", since_ms=0, days=400)

        self.assertEqual(calls, [0, 2001])
        self.assertEqual([point["close"] for point in points], [1.0, 2.0, 3.0])
        self.assertGreaterEqual(MAX_CANDLES_PER_REQUEST, 2000)

    def test_drops_non_positive_candles(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"t": 1_000, "o": 0, "h": 1, "l": 0, "c": 1, "v": 1},
                        _candle(2_000, 4.0),
                    ]
                },
            )

        client = MobulaClient(api_key="secret", transport=httpx.MockTransport(handler))
        points = client.fetch_ohlcv("mint", "solana", since_ms=0, days=1)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["close"], 4.0)

    def test_http_error_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="slow down")

        client = MobulaClient(api_key="secret", transport=httpx.MockTransport(handler))
        with self.assertRaises(ConnectorFetchError) as caught:
            client.fetch_ohlcv("mint", "solana", since_ms=0, days=1)
        self.assertIn("429", str(caught.exception))


class TokenAddressLookupTests(unittest.TestCase):
    def _create(self, path: Path, *, with_address_column: bool) -> None:
        conn = sqlite3.connect(path)
        address_sql = ", token_address TEXT" if with_address_column else ""
        conn.execute(
            f"""
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                exchange TEXT,
                source TEXT,
                status TEXT
                {address_sql}
            )
            """
        )
        conn.commit()
        conn.close()

    def test_missing_file_returns_none(self) -> None:
        missing = Path("/tmp/mobula-missing-portfolio.db")
        if missing.exists():
            missing.unlink()
        self.assertIsNone(
            lookup_onchain_token_address("BONK", "solana", database_path=missing)
        )
        self.assertFalse(missing.exists())

    def test_missing_column_returns_none(self) -> None:
        path = Path("/tmp/mobula-no-address-column.db")
        if path.exists():
            path.unlink()
        self._create(path, with_address_column=False)
        self.addCleanup(path.unlink)
        self.assertIsNone(
            lookup_onchain_token_address("BONK", "solana", database_path=path)
        )

    def test_reads_synced_address_and_skips_manual(self) -> None:
        path = Path("/tmp/mobula-token-address.db")
        if path.exists():
            path.unlink()
        self._create(path, with_address_column=True)
        self.addCleanup(path.unlink)
        conn = sqlite3.connect(path)
        conn.executemany(
            """
            INSERT INTO positions (symbol, exchange, source, status, token_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("BONK", "solana", "manual", "open", "manual-mint"),
                ("BONK", "solana", "synced", "closed", "closed-mint"),
                ("BONK", "Solana", "synced", "open", "open-mint"),
                ("BONK", "ethereum", "synced", "open", "0xeth"),
                ("WIF", "solana", "synced", "open", "   "),
            ],
        )
        conn.commit()
        conn.close()

        self.assertEqual(
            lookup_onchain_token_address("bonk", "SOLANA", database_path=path),
            "open-mint",
        )
        self.assertEqual(
            lookup_onchain_token_address("BONK", "ethereum", database_path=path),
            "0xeth",
        )
        self.assertIsNone(
            lookup_onchain_token_address("WIF", "solana", database_path=path)
        )


class OnChainPriceHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_price_history_cache()

    async def test_solana_and_ethereum_pass_exchange_as_chain_id(self) -> None:
        calls: List[tuple] = []

        class Recording:
            def fetch_ohlcv(self, address: str, chain_id: str, since_ms: int, *, days: int):
                calls.append((address, chain_id, days))
                return [
                    {
                        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
                        "open": 1.0,
                        "high": 2.0,
                        "low": 0.5,
                        "close": 1.5,
                        "price": 1.5,
                    }
                ]

        addresses = {
            ("BONK", "solana"): "mint-bonk",
            ("PEPE", "ethereum"): "0xpepe",
        }
        service = PriceHistoryService(
            token_address_lookup=lambda symbol, exchange: addresses.get((symbol, exchange)),
            mobula_client=Recording(),  # type: ignore[arg-type]
        )

        solana = await service.fetch("bonk", 7, "solana")
        ethereum = await service.fetch("pepe", 30, "Ethereum")

        self.assertEqual(solana.resolution_status, RESOLVED)
        self.assertEqual(ethereum.resolution_status, RESOLVED)
        self.assertEqual(calls, [("mint-bonk", "solana", 7), ("0xpepe", "ethereum", 30)])
        self.assertEqual(solana.points[0]["price"], 1.5)

    async def test_blank_token_address_skips_http(self) -> None:
        class Boom:
            def fetch_ohlcv(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
                raise AssertionError("Mobula was called without a token address")

        service = PriceHistoryService(
            token_address_lookup=lambda symbol, exchange: None,
            mobula_client=Boom(),  # type: ignore[arg-type]
        )
        result = await service.fetch("BONK", 7, "solana")
        self.assertEqual(result.resolution_status, NOT_FOUND)
        self.assertIn("No on-chain token address stored for BONK on solana", result.ambiguity_message or "")

    async def test_missing_api_key_is_reported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"unexpected request {request.url}")

        service = PriceHistoryService(
            token_address_lookup=lambda symbol, exchange: "mint",
            mobula_client=MobulaClient(api_key="  ", transport=httpx.MockTransport(handler)),
        )
        result = await service.fetch("BONK", 1, "solana")
        self.assertEqual(result.resolution_status, NOT_FOUND)
        self.assertIn("API key is not configured", result.ambiguity_message or "")

    async def test_binance_still_uses_connector_ohlcv(self) -> None:
        class Connector:
            def __init__(self) -> None:
                self.calls: List[tuple] = []

            def fetch_price_history_sync(self, market_pair: str, since_ms: int, *, days: int):
                self.calls.append((market_pair, days))
                return [
                    {
                        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.0,
                        "close": 10.5,
                        "price": 10.5,
                    }
                ]

        class Boom:
            def fetch_ohlcv(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
                raise AssertionError("CEX history must not call Mobula")

        connector = Connector()
        service = PriceHistoryService(
            token_address_lookup=lambda symbol, exchange: "should-not-be-read",
            mobula_client=Boom(),  # type: ignore[arg-type]
        )
        with patch(
            "src.services.price_history.get_connector_by_name",
            return_value=connector,
        ) as get_connector:
            result = await service.fetch("btc", 90, "binance")

        get_connector.assert_called_once_with("binance")
        self.assertEqual(result.resolution_status, RESOLVED)
        self.assertEqual(connector.calls, [("BTC/USDT", 90)])
        self.assertEqual(result.points[0]["close"], 10.5)


class VenueListingTests(unittest.TestCase):
    def test_mobula_config_is_not_a_synced_venue(self) -> None:
        from src.config.loader import list_configured_venues

        config = {
            "binance": {"api_key": "k"},
            "mobula": {"api_key": "m"},
            "ethereum": {"address": "0xabc", "hostname": "https://rpc.example"},
        }
        with patch("src.config.loader.load_config", return_value=config):
            keys = [venue["key"] for venue in list_configured_venues()]
        self.assertEqual(keys, ["binance", "ethereum"])


if __name__ == "__main__":
    unittest.main()
