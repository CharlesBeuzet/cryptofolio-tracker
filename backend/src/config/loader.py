"""Shared YAML configuration loader."""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_CONFIG_CACHE: Optional[Dict[str, Any]] = None

# Top-level config keys treated as self-custody / wallet providers.
_WALLET_VENUE_KEYS = frozenset({"hot_wallets", "wallets", "cold_wallets"})


def project_root() -> Path:
    """Repository root (four levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def config_path() -> Path:
    return project_root() / "settings" / "config.yaml"


def clear_config_cache() -> None:
    """Drop the in-memory config cache (call after writing config.yaml)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


def load_config() -> Dict[str, Any]:
    """Load settings/config.yaml once and cache the result."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    path = config_path()
    if not path.exists():
        _CONFIG_CACHE = {}
        return _CONFIG_CACHE

    with open(path, "r", encoding="utf-8") as handle:
        _CONFIG_CACHE = yaml.safe_load(handle) or {}

    return _CONFIG_CACHE


def get_section(name: str) -> Dict[str, Any]:
    """Return a config section or an empty dict."""
    return dict(load_config().get(name) or {})


def save_config(data: Dict[str, Any]) -> None:
    """Atomically write config.yaml and invalidate the cache."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".yaml.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(
            data,
            handle,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    tmp_path.replace(path)
    clear_config_cache()
    
def venue_display_name(key: str) -> str:
    """
    Human-readable label for a config provider key.

    Generic transform: replace underscores with spaces and capitalize each word
    (e.g. hot_wallets → Hot Wallets, my_exchange → My Exchange).
    """
    return " ".join(part.capitalize() for part in key.replace("_", " ").split())


def list_configured_venues() -> List[Dict[str, str]]:
    """
    Return data providers declared as top-level mapping sections in config.yaml.

    Each item has: key, display_name, kind ("exchange" | "wallet").
    Order matches YAML declaration order.
    """
    config = load_config()
    venues: List[Dict[str, str]] = []
    for key, value in config.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        kind = "wallet" if key in _WALLET_VENUE_KEYS else "exchange"
        venues.append(
            {
                "key": key,
                "display_name": venue_display_name(key),
                "kind": kind,
            }
        )
    return venues
