"""Read/update settings/config.yaml with secret masking for the Settings UI."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from ..config import loader
from ..connectors.registry import available_connector_names, list_available_connectors
from ..runtime import trigger_config_reload

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


def _section_is_active(section: Any) -> bool:
    """True when a YAML section is present for a developed connector (same rule as registry)."""
    return isinstance(section, dict) and bool(section)


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


def _catalog_by_name() -> Dict[str, Dict[str, Any]]:
    return {entry["name"]: entry for entry in list_available_connectors()}


def _is_configured(section: Dict[str, Any], meta: Dict[str, Any]) -> bool:
    """Exchange connectors need secrets; wallets need address + RPC hostname."""
    if meta.get("supports_address"):
        address = section.get("address")
        if not address or _is_placeholder(address):
            return False
        if meta.get("supports_hostname"):
            hostname = section.get("hostname")
            if not hostname or _is_placeholder(hostname):
                return False
        return True
    return _has_real_secret(section)


def get_public_config() -> Dict[str, Any]:
    """Return a UI-safe view of config.yaml (secrets masked)."""
    raw = loader.load_config()
    path = loader.config_path()
    catalog = list_available_connectors()
    catalog_map = {entry["name"]: entry for entry in catalog}

    exchanges: List[Dict[str, Any]] = []
    for name in available_connector_names():
        section = raw.get(name)
        if not _section_is_active(section):
            continue
        section = dict(section)
        meta = catalog_map.get(name, {})
        address = section.get("address")
        exchanges.append(
            {
                "name": name,
                "label": meta.get("label") or name.title(),
                "configured": _is_configured(section, meta),
                "api_key": _secret_field(section, "api_key"),
                "api_secret": _secret_field(section, "api_secret"),
                "passphrase": _secret_field(section, "passphrase"),
                "supports_passphrase": bool(meta.get("supports_passphrase")),
                "supports_hostname": bool(meta.get("supports_hostname")),
                "supports_address": bool(meta.get("supports_address")),
                "sandbox": bool(section["sandbox"]) if "sandbox" in section else None,
                "hostname": section.get("hostname"),
                "address": None if _is_placeholder(address) else (str(address).strip() if address else None),
            }
        )

    return {
        "exists": path.exists(),
        "relative_path": "settings/config.yaml",
        "available_connectors": catalog,
        "exchanges": exchanges,
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
    meta: Dict[str, Any],
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

    if meta.get("supports_address") and "address" in update:
        address = update.get("address")
        if address is None:
            pass
        elif str(address).strip() == "" or _is_placeholder(address):
            merged.pop("address", None)
        else:
            merged["address"] = str(address).strip()

    return merged


def update_config(
    exchanges: Optional[List[Dict[str, Any]]] = None,
    replace_exchanges: bool = False,
) -> Dict[str, Any]:
    """
    Merge UI updates into config.yaml.

    Secret fields: None/omitted keeps the existing value; "" clears it.
    When replace_exchanges is True, developed connector sections not present in
    `exchanges` are removed (so the UI list is the source of truth).
    Legacy `hot_wallets` sections are removed on any write.
    """
    current = deepcopy(loader.load_config())
    known = set(available_connector_names())
    catalog = _catalog_by_name()

    # Drop legacy nested hot_wallets block (replaced by ethereum connector sections).
    current.pop("hot_wallets", None)

    if exchanges is not None:
        if replace_exchanges:
            keep = {
                str(item.get("name") or "").strip().lower()
                for item in exchanges
            }
            for name in list(known):
                if name not in keep:
                    current.pop(name, None)

        for exchange_update in exchanges:
            name = str(exchange_update.get("name") or "").strip().lower()
            if name not in known:
                raise ValueError(
                    f"Unsupported connector: {name}. "
                    f"Available: {', '.join(sorted(known))}"
                )
            meta = catalog.get(name, {})
            existing = dict(current.get(name) or {})
            merged = _merge_exchange(existing, exchange_update, meta)

            if meta.get("supports_address"):
                address = merged.get("address")
                if not address or _is_placeholder(address):
                    raise ValueError(
                        f"{meta.get('label') or name}: wallet address is required."
                    )
                if meta.get("supports_hostname"):
                    hostname = merged.get("hostname")
                    if not hostname or _is_placeholder(hostname):
                        raise ValueError(
                            f"{meta.get('label') or name}: RPC URL is required."
                        )

            if merged:
                current[name] = merged
            elif name in current:
                del current[name]

    loader.save_config(current)
    trigger_config_reload()
    return get_public_config()
