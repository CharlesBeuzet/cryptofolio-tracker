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

    def test_get_public_config_masks_secrets(self) -> None:
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
        by_name = {ex["name"]: ex for ex in public["exchanges"]}

        self.assertTrue(by_name["binance"]["configured"])
        self.assertTrue(by_name["binance"]["api_key"]["is_set"])
        self.assertEqual(by_name["binance"]["api_key"]["hint"], "••••1234")
        self.assertNotIn("real-binance-key", str(public))

        self.assertFalse(by_name["okx"]["configured"])
        self.assertFalse(by_name["okx"]["api_key"]["is_set"])
        self.assertTrue(by_name["okx"]["supports_passphrase"])

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

    def test_update_replaces_hot_wallets(self) -> None:
        self._write({"hot_wallets": {"default_rpc": "https://old.example"}})
        config_settings.update_config(
            hot_wallets={
                "default_rpc": "https://eth.llamarpc.com",
                "rpc_urls": [{"chain": "ethereum", "url": "https://eth.llamarpc.com"}],
                "addresses": [
                    {
                        "address": "0xabc123",
                        "chain": "ethereum",
                        "tokens": [
                            {
                                "address": "0xtoken1",
                                "symbol": "USDC",
                                "decimals": 6,
                            }
                        ],
                    }
                ],
            }
        )
        saved = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["hot_wallets"]["default_rpc"], "https://eth.llamarpc.com")
        self.assertEqual(saved["hot_wallets"]["addresses"][0]["address"], "0xabc123")
        self.assertEqual(saved["hot_wallets"]["addresses"][0]["tokens"][0]["symbol"], "USDC")


if __name__ == "__main__":
    unittest.main()
