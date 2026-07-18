"""Load exchange connectors from settings/config.yaml."""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .base import BaseConnector
from .binance import BinanceConnector
from .okx import OkxConnector

_CONNECTOR_FACTORIES = {
    "binance": BinanceConnector,
    "okx": OkxConnector,
}

# Field metadata for the Settings UI (must stay aligned with each connector __init__).
_CONNECTOR_SPECS: Dict[str, Dict[str, Any]] = {
    "binance": {
        "label": "Binance",
        "supports_passphrase": False,
        "supports_hostname": False,
        "required_secrets": ("api_key", "api_secret"),
    },
    "okx": {
        "label": "OKX",
        "supports_passphrase": True,
        "supports_hostname": True,
        "required_secrets": ("api_key", "api_secret", "passphrase"),
    },
}


def available_connector_names() -> List[str]:
    """Names of connectors implemented in this codebase."""
    return list(_CONNECTOR_FACTORIES.keys())


def list_available_connectors() -> List[Dict[str, Any]]:
    """Return catalog entries for the Settings add-connector picker."""
    catalog: List[Dict[str, Any]] = []
    for name in available_connector_names():
        spec = _CONNECTOR_SPECS.get(name, {})
        catalog.append(
            {
                "name": name,
                "label": spec.get("label") or name.title(),
                "supports_passphrase": bool(spec.get("supports_passphrase")),
                "supports_hostname": bool(spec.get("supports_hostname")),
                "required_secrets": list(spec.get("required_secrets") or ("api_key", "api_secret")),
            }
        )
    return catalog


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "settings" / "config.yaml"


def load_connectors(config_path: Optional[str] = None) -> List[BaseConnector]:
    """Instantiate all connectors that have configuration sections."""
    path = Path(config_path) if config_path else _default_config_path()
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    connectors: List[BaseConnector] = []
    for name, factory in _CONNECTOR_FACTORIES.items():
        section = config.get(name)
        if not section:
            continue
        try:
            connectors.append(factory(section))
        except Exception as exc:
            print(f"Failed to initialize {name} connector: {exc}")
    return connectors


def get_connector_by_name(
    exchange: str,
    config_path: Optional[str] = None,
) -> Optional[BaseConnector]:
    """Return a connector instance for one exchange name, or None if unavailable."""
    normalized = exchange.strip().lower()
    for connector in load_connectors(config_path):
        if connector.name == normalized:
            return connector
    return None
