"""Read/update settings/config.yaml with secret masking for the Settings UI."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from ..config import loader
from ..connectors.registry import available_connector_names, list_available_connectors
from ..runtime import trigger_config_reload
from .mobula_client import ALLOWED_BLOCKCHAINS, chain_slug

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


def _real_wallets(section: Dict[str, Any]) -> List[str]:
    wallets = section.get("wallets") or []
    if isinstance(wallets, str):
        wallets = [line.strip() for line in wallets.splitlines() if line.strip()]
    return [str(item).strip() for item in wallets if str(item).strip() and not _is_placeholder(item)]


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
    if meta.get("supports_wallets"):
        chains = section.get("blockchains") or []
        return bool(_real_wallets(section) and chains and _has_real_secret(section))
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
                "supports_wallets": bool(meta.get("supports_wallets")),
                "supports_blockchains": bool(meta.get("supports_blockchains")),
                "sandbox": bool(section["sandbox"]) if "sandbox" in section else None,
                "hostname": section.get("hostname"),
                "address": None if _is_placeholder(address) else (str(address).strip() if address else None),
                "wallets": _wallets_text(section.get("wallets")),
                "blockchains": _blockchains_text(section.get("blockchains")),
            }
        )

    return {
        "exists": path.exists(),
        "relative_path": "settings/config.yaml",
        "available_connectors": catalog,
        "exchanges": exchanges,
    }


def _wallets_text(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    lines = [str(item).strip() for item in value if str(item).strip()]
    return "\n".join(lines) or None


def _blockchains_text(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    names = [str(item).strip() for item in value if str(item).strip()]
    return ", ".join(names) or None


def _parse_lines(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        parts = str(raw).splitlines()
    out: List[str] = []
    for part in parts:
        text = part.strip()
        if text and text not in out:
            out.append(text)
    return out


def _parse_blockchains(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        chunks = [str(item) for item in raw]
    else:
        chunks = str(raw).replace("\n", ",").split(",")
    slugs: List[str] = []
    for chunk in chunks:
        text = chunk.strip()
        if not text:
            continue
        slug = chain_slug(text)
        if slug is None or slug not in ALLOWED_BLOCKCHAINS:
            allowed = ", ".join(ALLOWED_BLOCKCHAINS)
            raise ValueError(f"Unsupported blockchain '{text}'. Allowed: {allowed}.")
        if slug not in slugs:
            slugs.append(slug)
    return slugs


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

    if meta.get("supports_wallets") and "wallets" in update and update.get("wallets") is not None:
        wallets = _parse_lines(update.get("wallets"))
        if wallets:
            merged["wallets"] = wallets
        else:
            merged.pop("wallets", None)

    if (
        meta.get("supports_blockchains")
        and "blockchains" in update
        and update.get("blockchains") is not None
    ):
        chains = _parse_blockchains(update.get("blockchains"))
        if chains:
            merged["blockchains"] = chains
        else:
            merged.pop("blockchains", None)

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

    # Retired wallet shapes. The next Settings save drops them.
    current.pop("hot_wallets", None)
    current.pop("ethereum", None)

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

            label = meta.get("label") or name
            if meta.get("supports_address"):
                address = merged.get("address")
                if not address or _is_placeholder(address):
                    raise ValueError(f"{label}: wallet address is required.")
                if meta.get("supports_hostname"):
                    hostname = merged.get("hostname")
                    if not hostname or _is_placeholder(hostname):
                        raise ValueError(f"{label}: RPC URL is required.")
            if meta.get("supports_wallets"):
                if not _real_wallets(merged):
                    raise ValueError(f"{label}: at least one wallet address is required.")
                if not merged.get("blockchains"):
                    raise ValueError(f"{label}: at least one blockchain is required.")
                if not _has_real_secret(merged):
                    raise ValueError(f"{label}: API key is required.")

            if merged:
                current[name] = merged
            elif name in current:
                del current[name]

    loader.save_config(current)
    trigger_config_reload()
    return get_public_config()
