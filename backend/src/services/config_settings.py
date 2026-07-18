"""Read/update settings/config.yaml with secret masking for the Settings UI."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from ..config import loader
from ..runtime import trigger_config_reload

# Exchange sections supported by the example config (connectors may lag).
EXCHANGE_SECTIONS = ("binance", "okx", "coinbase")
SECRET_KEYS = ("api_key", "api_secret", "passphrase")

# Placeholder / example values that should not count as "configured".
_PLACEHOLDER_FRAGMENTS = (
    "your_",
    "_here",
    "changeme",
    "example",
    "placeholder",
    "0xyourethereumaddresshere",
    "0xtokencontractaddress",
)


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    if not text:
        return True
    if text.endswith("here") and ("your_" in text or "address" in text):
        return True
    return any(fragment in text for fragment in _PLACEHOLDER_FRAGMENTS)


def _has_real_secret(section: Dict[str, Any]) -> bool:
    for key in SECRET_KEYS:
        raw = section.get(key)
        if raw and not _is_placeholder(raw):
            return True
    return False


def mask_secret(value: Any) -> Tuple[bool, Optional[str]]:
    """Return (is_set, hint). Hint shows last 4 chars when set."""
    if value is None or _is_placeholder(value):
        return False, None
    text = str(value).strip()
    if not text:
        return False, None
    if len(text) <= 4:
        return True, "••••"
    return True, f"••••{text[-4:]}"


def _secret_field(section: Dict[str, Any], key: str) -> Dict[str, Any]:
    is_set, hint = mask_secret(section.get(key))
    return {"is_set": is_set, "hint": hint}


def get_public_config() -> Dict[str, Any]:
    """Return a UI-safe view of config.yaml (secrets masked)."""
    raw = loader.load_config()
    path = loader.config_path()

    exchanges: List[Dict[str, Any]] = []
    for name in EXCHANGE_SECTIONS:
        section = dict(raw.get(name) or {})
        exchanges.append(
            {
                "name": name,
                "configured": _has_real_secret(section),
                "api_key": _secret_field(section, "api_key"),
                "api_secret": _secret_field(section, "api_secret"),
                "passphrase": _secret_field(section, "passphrase"),
                "supports_passphrase": name in ("okx", "coinbase"),
                "sandbox": bool(section["sandbox"]) if "sandbox" in section else None,
                "hostname": section.get("hostname"),
            }
        )

    hw = dict(raw.get("hot_wallets") or {})
    rpc_urls_raw = hw.get("rpc_urls") or {}
    rpc_urls = [
        {"chain": str(chain), "url": str(url)}
        for chain, url in rpc_urls_raw.items()
        if chain and url
    ]
    addresses: List[Dict[str, Any]] = []
    for entry in hw.get("addresses") or []:
        if not isinstance(entry, dict):
            continue
        tokens = []
        for token in entry.get("tokens") or []:
            if not isinstance(token, dict):
                continue
            tokens.append(
                {
                    "address": str(token.get("address") or ""),
                    "symbol": str(token.get("symbol") or ""),
                    "decimals": int(token.get("decimals") or 18),
                }
            )
        addresses.append(
            {
                "address": str(entry.get("address") or ""),
                "chain": str(entry.get("chain") or "ethereum"),
                "tokens": tokens,
            }
        )

    return {
        "exists": path.exists(),
        "relative_path": "settings/config.yaml",
        "exchanges": exchanges,
        "hot_wallets": {
            "default_rpc": hw.get("default_rpc"),
            "rpc_urls": rpc_urls,
            "addresses": addresses,
        },
    }


def _apply_secret(
    target: Dict[str, Any],
    key: str,
    new_value: Optional[str],
) -> None:
    """None = leave unchanged; empty string = clear; otherwise set."""
    if new_value is None:
        return
    if new_value.strip() == "":
        target.pop(key, None)
        return
    target[key] = new_value.strip()


def _merge_exchange(
    current: Dict[str, Any],
    update: Dict[str, Any],
) -> Dict[str, Any]:
    merged = deepcopy(current) if current else {}

    _apply_secret(merged, "api_key", update.get("api_key"))
    _apply_secret(merged, "api_secret", update.get("api_secret"))
    _apply_secret(merged, "passphrase", update.get("passphrase"))

    if "sandbox" in update and update["sandbox"] is not None:
        merged["sandbox"] = bool(update["sandbox"])

    if "hostname" in update:
        hostname = update["hostname"]
        if hostname is None:
            pass
        elif str(hostname).strip() == "":
            merged.pop("hostname", None)
        else:
            merged["hostname"] = str(hostname).strip()

    return merged


def _build_hot_wallets(update: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    default_rpc = update.get("default_rpc")
    if default_rpc is not None and str(default_rpc).strip():
        result["default_rpc"] = str(default_rpc).strip()

    rpc_urls: Dict[str, str] = {}
    for item in update.get("rpc_urls") or []:
        chain = str(item.get("chain") or "").strip()
        url = str(item.get("url") or "").strip()
        if chain and url:
            rpc_urls[chain] = url
    if rpc_urls:
        result["rpc_urls"] = rpc_urls

    addresses: List[Dict[str, Any]] = []
    for item in update.get("addresses") or []:
        address = str(item.get("address") or "").strip()
        if not address or _is_placeholder(address):
            continue
        entry: Dict[str, Any] = {
            "address": address,
            "chain": str(item.get("chain") or "ethereum").strip() or "ethereum",
        }
        tokens: List[Dict[str, Any]] = []
        for token in item.get("tokens") or []:
            token_addr = str(token.get("address") or "").strip()
            if not token_addr or _is_placeholder(token_addr):
                continue
            tokens.append(
                {
                    "address": token_addr,
                    "symbol": str(token.get("symbol") or "").strip(),
                    "decimals": int(token.get("decimals") if token.get("decimals") is not None else 18),
                }
            )
        if tokens:
            entry["tokens"] = tokens
        addresses.append(entry)
    if addresses:
        result["addresses"] = addresses

    return result


def update_config(
    exchanges: Optional[List[Dict[str, Any]]] = None,
    hot_wallets: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge UI updates into config.yaml.

    Secret fields: None/omitted keeps the existing value; "" clears it.
    Hot wallets: when provided, the whole section is replaced by the payload.
    """
    current = deepcopy(loader.load_config())

    if exchanges:
        for exchange_update in exchanges:
            name = str(exchange_update.get("name") or "").strip().lower()
            if name not in EXCHANGE_SECTIONS:
                raise ValueError(f"Unsupported exchange section: {name}")
            existing = dict(current.get(name) or {})
            merged = _merge_exchange(existing, exchange_update)
            # Keep section if it has any meaningful content
            if merged:
                current[name] = merged
            elif name in current:
                del current[name]

    if hot_wallets is not None:
        built = _build_hot_wallets(hot_wallets)
        if built:
            current["hot_wallets"] = built
        else:
            current.pop("hot_wallets", None)

    loader.save_config(current)
    trigger_config_reload()
    return get_public_config()
