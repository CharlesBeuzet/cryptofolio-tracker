"""Mobula HTTP client and payload parsing.

Free-tier budget: 10_000 credits / month and 1 request / second.
Portfolio is one call for every wallet, scoped to the configured chains.
Activity is one wallet per call. OHLCV is one call per chart.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

import httpx

from ..utils.data_quality import ConnectorFetchError, positive_finite

API_ROOT = "https://api.mobula.io"
NATIVE_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
STABLE_SYMBOLS = frozenset({"USDC", "USDT"})
ACTIVITY_PAGE_SIZE = 100

# Mobula chain ids → the slug stored on positions.exchange / orders.exchange.
CHAIN_ID_TO_SLUG: Dict[str, str] = {
    "evm:1": "ethereum",
    "evm:8453": "base",
    "evm:42161": "arbitrum",
    "evm:137": "polygon",
    "evm:43114": "avalanche",
    "evm:56": "bnb",
    "evm:10": "optimism",
    "evm:146": "sonic",
    "solana:solana": "solana",
}
SLUG_TO_CHAIN_ID: Dict[str, str] = {
    slug: chain_id for chain_id, slug in CHAIN_ID_TO_SLUG.items()
}
ALLOWED_BLOCKCHAINS = (
    "ethereum",
    "base",
    "arbitrum",
    "polygon",
    "avalanche",
    "bnb",
    "optimism",
    "sonic",
    "solana",
)
_SLUG_ALIASES = {
    "ethereum": "ethereum",
    "eth": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "polygon": "polygon",
    "matic": "polygon",
    "avalanche": "avalanche",
    "avax": "avalanche",
    "bnb": "bnb",
    "bsc": "bnb",
    "optimism": "optimism",
    "op": "optimism",
    "sonic": "sonic",
    "solana": "solana",
    "sol": "solana",
}

# Native placeholder has no pool. Charts use the wrapped token on that chain.
WRAPPED_NATIVE: Dict[str, str] = {
    "ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "base": "0x4200000000000000000000000000000000000006",
    "optimism": "0x4200000000000000000000000000000000000006",
    "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "polygon": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "avalanche": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    "bnb": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "sonic": "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38",
    "solana": "So11111111111111111111111111111111111111112",
}

_FORBIDDEN_PARAMS = frozenset(
    {
        "fetchallchains",
        "backfilltransfers",
        "shouldfetchpricechange",
        "fetchuntrackedhistory",
    }
)
_SYMBOL_RE = re.compile(r"[^A-Z0-9]")


def chain_slug(value: Optional[str]) -> Optional[str]:
    """Normalize a Mobula chain id or alias to a stored slug."""
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in CHAIN_ID_TO_SLUG:
        return CHAIN_ID_TO_SLUG[raw]
    if raw in _SLUG_ALIASES:
        return _SLUG_ALIASES[raw]
    if ":" in raw:
        _prefix, _, rest = raw.partition(":")
        if rest in _SLUG_ALIASES:
            return _SLUG_ALIASES[rest]
        if rest in CHAIN_ID_TO_SLUG:
            return CHAIN_ID_TO_SLUG[rest]
    return None


def normalize_token_address(address: str) -> str:
    """Lowercase EVM addresses. Leave Solana mints unchanged."""
    text = str(address).strip()
    if text.lower().startswith("0x"):
        return text.lower()
    return text


def chart_address(chain: str, token_address: str) -> str:
    """Contract sent to OHLCV. Native placeholders use the wrapped token."""
    slug = chain_slug(chain) or chain
    token = str(token_address).strip()
    lowered = token.lower()
    if lowered in {NATIVE_PLACEHOLDER, "native"}:
        wrapped = WRAPPED_NATIVE.get(slug)
        if wrapped:
            return normalize_token_address(wrapped) if wrapped.startswith("0x") else wrapped
    return normalize_token_address(token) if lowered.startswith("0x") else token


def portfolio_params(wallets: Iterable[str], blockchains: Iterable[str]) -> Dict[str, str]:
    """Query string for one portfolio call. Never opts into expensive flags."""
    return {
        "wallets": ",".join(wallets),
        "blockchains": ",".join(blockchains),
        "cache": "true",
        "stale": "3600",
        "filterSpam": "true",
        "minliq": "0",
    }


def activity_params(
    wallet: str,
    blockchains: Iterable[str],
    *,
    limit: int = ACTIVITY_PAGE_SIZE,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
) -> Dict[str, str]:
    """One activity page. chainIds are Mobula ids, not the slugs we store."""
    chain_ids: List[str] = []
    for name in blockchains:
        slug = chain_slug(name)
        chain_id = SLUG_TO_CHAIN_ID.get(slug or "")
        if chain_id and chain_id not in chain_ids:
            chain_ids.append(chain_id)
    params = {
        "wallet": wallet,
        "chainIds": ",".join(chain_ids),
        "limit": str(limit),
        "order": "desc",
        "filterSpam": "true",
    }
    if from_ms is not None:
        params["from"] = str(int(from_ms))
    if to_ms is not None:
        params["to"] = str(int(to_ms))
    return params


def ohlcv_params(
    address: str,
    chain: str,
    *,
    period: str,
    amount: int,
    from_ms: int,
) -> Dict[str, str]:
    return {
        "address": address,
        "chainId": chain,
        "period": period,
        "amount": str(amount),
        "from": str(int(from_ms)),
        "usd": "true",
    }


def ohlcv_window(days: int) -> tuple[str, int]:
    """One candle request that covers the chart range (Mobula caps amount at 2000)."""
    if days <= 1:
        return "1h", 24
    if days <= 7:
        return "1h", 24 * 7
    if days <= 30:
        return "4h", (24 * 30) // 4
    if days <= 365:
        return "1d", min(days, 400)
    return "1w", min(520, max(1, days // 7))


def _reject_forbidden(params: Mapping[str, Any]) -> None:
    found = {key for key in params if str(key).lower() in _FORBIDDEN_PARAMS}
    if found:
        raise ConnectorFetchError(
            f"Refusing Mobula parameters that blow the free-tier budget: {sorted(found)}"
        )


def _fit_symbol(base: str, suffix: Optional[str] = None) -> str:
    cleaned = _SYMBOL_RE.sub("", (base or "").upper()) or "TOKEN"
    if not suffix:
        return cleaned[:20]
    extra = _SYMBOL_RE.sub("", suffix.upper())[:6] or "X"
    room = 20 - len(extra) - 1
    if room < 1:
        return extra[:20]
    return f"{cleaned[:room]}-{extra}"


def _portfolio_assets(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        assets = data.get("assets") or []
    elif isinstance(data, list):
        assets = data
    else:
        assets = payload.get("assets") or []
    if not isinstance(assets, list):
        return []
    return [row for row in assets if isinstance(row, Mapping)]


def _contract_rows(asset: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in ("contracts_balances", "contractsBalances"):
        value = asset.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return []


def portfolio_rows(
    payload: Mapping[str, Any], allowed_slugs: Iterable[str]
) -> List[Dict[str, Any]]:
    """One balance row per chain + contract. Quantities from several wallets are summed."""
    allowed = {chain_slug(slug) for slug in allowed_slugs}
    allowed.discard(None)
    assets = _portfolio_assets(payload)
    aggregated: Dict[tuple, Dict[str, Any]] = {}
    saw_contract = False
    for asset in assets:
        meta = asset.get("asset") if isinstance(asset.get("asset"), Mapping) else {}
        symbol = str(meta.get("symbol") or asset.get("symbol") or "").strip().upper()
        name = meta.get("name") or asset.get("name")
        price = asset.get("price")
        if price is None and isinstance(meta, Mapping):
            price = meta.get("price")
        contracts = _contract_rows(asset)
        if contracts:
            saw_contract = True
        if not symbol:
            continue
        for contract in contracts:
            address = contract.get("address") or contract.get("contract")
            chain_raw = (
                contract.get("chainId")
                or contract.get("chain_id")
                or contract.get("blockchain")
            )
            slug = chain_slug(str(chain_raw) if chain_raw is not None else None)
            if not address or slug not in allowed:
                continue
            qty = positive_finite(contract.get("balance"))
            if qty is None:
                qty = positive_finite(contract.get("amount"))
            if qty is None:
                continue
            token = normalize_token_address(str(address))
            key = (slug, token)
            spot = positive_finite(price)
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = {
                    "symbol": symbol,
                    "name": name,
                    "quantity": qty,
                    "exchange": slug,
                    "token_address": token,
                    "price": spot,
                }
            else:
                current["quantity"] += qty
                if current.get("price") is None and spot is not None:
                    current["price"] = spot
    if assets and not saw_contract:
        raise ConnectorFetchError(
            "Mobula portfolio response had assets but no contract balances"
        )
    return _disambiguate_symbols(list(aggregated.values()))


def _disambiguate_symbols(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same ticker, same chain, two contracts: keep one plain symbol and suffix the rest."""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["exchange"], row["symbol"]), []).append(row)
    out: List[Dict[str, Any]] = []
    for (_exchange, symbol), items in groups.items():
        items.sort(key=lambda item: item["token_address"])
        used: set[str] = set()
        for index, item in enumerate(items):
            if index == 0:
                candidate = _fit_symbol(symbol)
            else:
                candidate = _fit_symbol(symbol, item["token_address"][-4:])
            base = candidate
            n = 2
            while candidate in used:
                candidate = _fit_symbol(base, str(n))
                n += 1
            used.add(candidate)
            item["symbol"] = candidate
            if item.get("price") is None:
                item.pop("price", None)
            out.append(item)
    return out


def extract_transactions(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if isinstance(data, dict):
        for key in ("transactions", "activity", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
    return []


def transaction_time_ms(tx: Mapping[str, Any]) -> Optional[int]:
    raw = tx.get("txDateMs")
    if raw is None:
        raw = tx.get("timestamp")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def external_order_id(tx_hash: str, side: str, contract: str) -> str:
    token = normalize_token_address(contract)
    return f"{tx_hash}:{side}:{token}"[:160]


def _asset_fields(asset: Mapping[str, Any]) -> tuple[str, str, Optional[str]]:
    symbol = str(asset.get("symbol") or "").strip().upper()
    contract = asset.get("contract") or asset.get("address")
    name = asset.get("name")
    token = normalize_token_address(str(contract)) if contract else ""
    return symbol, token, str(name) if name else None


def _orders_from_swap(
    tx_hash: str,
    executed_at: datetime,
    slug: str,
    action: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Price each leg from the other leg, not from the catalogue spot."""
    asset_in = action.get("swapAssetIn") if isinstance(action.get("swapAssetIn"), Mapping) else {}
    asset_out = action.get("swapAssetOut") if isinstance(action.get("swapAssetOut"), Mapping) else {}
    amount_in = positive_finite(action.get("swapAmountIn"))
    amount_out = positive_finite(action.get("swapAmountOut"))
    if amount_in is None or amount_out is None:
        return []
    sym_in, token_in, name_in = _asset_fields(asset_in)
    sym_out, token_out, name_out = _asset_fields(asset_out)
    if not sym_in or not sym_out or not token_in or not token_out:
        return []

    usd = positive_finite(action.get("swapAmountUsd"))
    if sym_out in STABLE_SYMBOLS:
        price_out = 1.0
        price_in = amount_out / amount_in
    elif sym_in in STABLE_SYMBOLS:
        price_in = 1.0
        price_out = amount_in / amount_out
    elif usd is not None:
        price_in = usd / amount_in
        price_out = usd / amount_out
    else:
        return []
    if positive_finite(price_in) is None or positive_finite(price_out) is None:
        return []

    return [
        {
            "symbol": _fit_symbol(sym_in),
            "name": name_in,
            "token_address": token_in,
            "type": "buy",
            "quantity": amount_in,
            "price": price_in,
            "executed_at": executed_at,
            "exchange": slug,
            "external_order_id": external_order_id(tx_hash, "buy", token_in),
        },
        {
            "symbol": _fit_symbol(sym_out),
            "name": name_out,
            "token_address": token_out,
            "type": "sell",
            "quantity": amount_out,
            "price": price_out,
            "executed_at": executed_at,
            "exchange": slug,
            "external_order_id": external_order_id(tx_hash, "sell", token_out),
        },
    ]


def orders_from_transaction(tx: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Turn one activity transaction into buy/sell rows. Transfers are ignored."""
    tx_hash = str(tx.get("txHash") or tx.get("hash") or "").strip()
    tx_ms = transaction_time_ms(tx)
    slug = chain_slug(str(tx.get("chainId") or tx.get("chain_id") or ""))
    if not tx_hash or tx_ms is None or not slug:
        return []
    executed_at = datetime.fromtimestamp(tx_ms / 1000.0, tz=timezone.utc).replace(
        tzinfo=None
    )
    actions = tx.get("actions") or []
    rows: List[Dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, Mapping) or action.get("model") != "swap":
            continue
        rows.extend(_orders_from_swap(tx_hash, executed_at, slug, action))
    return rows


def parse_ohlcv(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Normalize Mobula candles to the chart row shape used by the price service."""
    data = payload.get("data")
    rows: Any = data
    if isinstance(data, dict):
        rows = data.get("candles") or data.get("ohlcv") or data.get("data") or []
    if not isinstance(rows, list):
        return []
    points: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if isinstance(row, Mapping):
            ts_raw = row.get("time") or row.get("timestamp") or row.get("t")
            open_ = row.get("open")
            high = row.get("high")
            low = row.get("low")
            close = row.get("close")
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            ts_raw, open_, high, low, close = row[0], row[1], row[2], row[3], row[4]
        else:
            continue
        try:
            ts_ms = int(ts_raw)
        except (TypeError, ValueError):
            continue
        if ts_ms in seen:
            continue
        open_n = positive_finite(open_)
        high_n = positive_finite(high)
        low_n = positive_finite(low)
        close_n = positive_finite(close)
        if None in (open_n, high_n, low_n, close_n):
            continue
        seen.add(ts_ms)
        points.append(
            {
                "timestamp": datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
                "open": open_n,
                "high": high_n,
                "low": low_n,
                "close": close_n,
                "price": close_n,
            }
        )
    points.sort(key=lambda point: point["timestamp"])
    return points


class MobulaClient:
    """Sync HTTP client. The scheduler calls it outside the FastAPI event loop."""

    def __init__(
        self,
        api_key: str,
        *,
        http: Optional[httpx.Client] = None,
        min_interval: float = 1.05,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.api_key = api_key
        self._http = http or httpx.Client(base_url=API_ROOT, timeout=30.0)
        self._min_interval = min_interval
        self._sleeper = sleeper
        self._clock = clock
        self._last: Optional[float] = None

    def get(self, path: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        _reject_forbidden(params)
        self._throttle()
        try:
            response = self._http.get(
                path,
                params=dict(params),
                headers={"Authorization": self.api_key},
            )
        except httpx.HTTPError as exc:
            raise ConnectorFetchError(f"Mobula {path} failed: {exc}") from exc
        if response.status_code >= 400:
            raise ConnectorFetchError(
                f"Mobula {path} HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorFetchError(f"Mobula {path} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ConnectorFetchError(f"Mobula {path} returned an unexpected payload")
        if payload.get("error") and payload.get("data") is None:
            raise ConnectorFetchError(f"Mobula {path}: {payload.get('error')}")
        return payload

    def portfolio(self, wallets: Iterable[str], blockchains: Iterable[str]) -> Dict[str, Any]:
        wallets = list(wallets)
        blockchains = list(blockchains)
        if not wallets or not blockchains:
            raise ConnectorFetchError("Mobula portfolio needs wallets and blockchains")
        return self.get(
            "/api/1/wallet/portfolio",
            portfolio_params(wallets, blockchains),
        )

    def activity(
        self,
        wallet: str,
        blockchains: Iterable[str],
        *,
        from_ms: Optional[int] = None,
        to_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.get(
            "/api/2/wallet/activity",
            activity_params(
                wallet,
                blockchains,
                from_ms=from_ms,
                to_ms=to_ms,
            ),
        )

    def ohlcv(
        self,
        address: str,
        chain: str,
        *,
        period: str,
        amount: int,
        from_ms: int,
    ) -> Dict[str, Any]:
        return self.get(
            "/api/2/token/ohlcv-history",
            ohlcv_params(
                address,
                chain,
                period=period,
                amount=amount,
                from_ms=from_ms,
            ),
        )

    def _throttle(self) -> None:
        now = self._clock()
        if self._last is not None:
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                self._sleeper(wait)
                now = self._clock()
        self._last = now
