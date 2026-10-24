"""Unit tests for config settings (uses an isolated temp YAML file)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from src.config import loader
from src.services import config_settings


class ConfigSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_file = Path(self._tmpdir.name) / "config.yaml"
        self._path_patch = patch.object(loader, "config_path", return_value=self.config_file)
        self._reload_patch = patch.object(config_settings, "trigger_config_reload")
        self._path_patch.start()
        self._reload_patch.start()
        loader.clear_config_cache()

    def tearDown(self) -> None:
        self._reload_patch.stop()
        self._path_patch.stop()
        loader.clear_config_cache()
        self._tmpdir.cleanup()

    def _write(self, data: dict) -> None:
        with open(self.config_file, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle)
        loader.clear_config_cache()

    def test_get_public_config_masks_secrets_and_lists_active_only(self) -> None:
        self._write(
            {
                "binance": {
                    "api_key": "real-binance-key-1234",
                    "api_secret": "real-binance-secret-5678",
                },
                "okx": {
                    "api_key": "your_okx_api_key_here",
                    "api_secret": "your_okx_api_secret_here",
                    "passphrase": "your_okx_passphrase_here",
                },
            }
        )
        public = config_settings.get_public_config()
        names = [ex["name"] for ex in public["exchanges"]]

        # Both sections exist in YAML → both are active cards
        self.assertEqual(names, ["binance", "okx"])
        by_name = {ex["name"]: ex for ex in public["exchanges"]}
        self.assertTrue(by_name["binance"]["configured"])
        self.assertEqual(by_name["binance"]["api_key"]["hint"], "••••1234")
        self.assertNotIn("real-binance-key", str(public))
        self.assertFalse(by_name["okx"]["configured"])

        available_names = {item["name"] for item in public["available_connectors"]}
        self.assertEqual(available_names, {"binance", "okx", "mobula"})

    def test_update_keeps_secret_when_omitted(self) -> None:
        self._write(
            {
                "binance": {
                    "api_key": "keep-me-key-abcd",
                    "api_secret": "keep-me-secret-efgh",
                }
            }
        )
        config_settings.update_config(
            exchanges=[{"name": "binance", "hostname": "openapi.example"}],
        )
        saved = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["binance"]["api_key"], "keep-me-key-abcd")
        self.assertEqual(saved["binance"]["api_secret"], "keep-me-secret-efgh")
        self.assertEqual(saved["binance"]["hostname"], "openapi.example")

    def test_replace_exchanges_removes_missing(self) -> None:
        self._write(
            {
                "binance": {"api_key": "k1", "api_secret": "s1"},
                "okx": {"api_key": "k2", "api_secret": "s2", "passphrase": "p2"},
            }
        )
        config_settings.update_config(
            exchanges=[{"name": "binance"}],
            replace_exchanges=True,
        )
        saved = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        self.assertIn("binance", saved)
        self.assertNotIn("okx", saved)

    def test_add_new_connector(self) -> None:
        self._write({"binance": {"api_key": "k1", "api_secret": "s1"}})
        config_settings.update_config(
            exchanges=[
                {"name": "binance"},
                {
                    "name": "okx",
                    "api_key": "new-okx-key",
                    "api_secret": "new-okx-secret",
                    "passphrase": "new-okx-pass",
                },
            ],
            replace_exchanges=True,
        )
        saved = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["okx"]["api_key"], "new-okx-key")
        self.assertEqual(saved["okx"]["passphrase"], "new-okx-pass")

    def test_mobula_requires_wallets_and_chains(self) -> None:
        self._write({})
        with self.assertRaises(ValueError) as ctx:
            config_settings.update_config(
                exchanges=[{"name": "mobula", "api_key": "real-mobula-key-1234"}],
                replace_exchanges=True,
            )
        self.assertIn("wallet address is required", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            config_settings.update_config(
                exchanges=[
                    {
                        "name": "mobula",
                        "api_key": "real-mobula-key-1234",
                        "wallets": "So11111111111111111111111111111111111111112",
                    }
                ],
                replace_exchanges=True,
            )
        self.assertIn("blockchain is required", str(ctx.exception))

    def test_mobula_rejects_unknown_blockchain(self) -> None:
        self._write({})
        with self.assertRaises(ValueError) as ctx:
            config_settings.update_config(
                exchanges=[
                    {
                        "name": "mobula",
                        "api_key": "real-mobula-key-1234",
                        "wallets": "So11111111111111111111111111111111111111112",
                        "blockchains": "solana, fantom",
                    }
                ],
                replace_exchanges=True,
            )
        self.assertIn("Unsupported blockchain", str(ctx.exception))

    def test_add_mobula_connector_drops_retired_ethereum(self) -> None:
        self._write(
            {
                "hot_wallets": {"default_rpc": "https://old.example"},
                "ethereum": {
                    "hostname": "https://eth.llamarpc.com",
                    "address": "0xabc123",
                },
            }
        )
        config_settings.update_config(
            exchanges=[
                {
                    "name": "mobula",
                    "api_key": "real-mobula-key-1234",
                    "wallets": "WalletOne\nWalletTwo",
                    "blockchains": "Solana, evm:1",
                }
            ],
            replace_exchanges=True,
        )
        saved = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        self.assertNotIn("hot_wallets", saved)
        self.assertNotIn("ethereum", saved)
        self.assertEqual(saved["mobula"]["api_key"], "real-mobula-key-1234")
        self.assertEqual(saved["mobula"]["wallets"], ["WalletOne", "WalletTwo"])
        self.assertEqual(saved["mobula"]["blockchains"], ["solana", "ethereum"])
        public = config_settings.get_public_config()
        mobula = next(ex for ex in public["exchanges"] if ex["name"] == "mobula")
        self.assertTrue(mobula["configured"])
        self.assertTrue(mobula["supports_wallets"])
        self.assertEqual(mobula["wallets"], "WalletOne\nWalletTwo")
        self.assertEqual(mobula["blockchains"], "solana, ethereum")
        self.assertEqual(mobula["api_key"]["hint"], "••••1234")
        self.assertNotIn("real-mobula-key", str(public))


if __name__ == "__main__":
    unittest.main()
