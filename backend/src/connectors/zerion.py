"""Zerion EVM wallet connector (positions + transactions + CoinGecko charts)."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from ..utils.data_quality import ConnectorFetchError, positive_finite
from .base import BaseConnector

_DEFAULT_API_BASE = "https://api.zerion.io"
_COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
_HTTP_TIMEOUT = 30.0
_TX_PAGE_SIZE = 100
_TX_MAX_PAGES = 20

# Zerion chain id → CoinGecko asset platform (contract charts).
_COINGECKO_PLATFORM_BY_CHAIN: Dict[str, str] = {
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "optimism": "optimistic-ethereum",
    "polygon": "polygon-pos",
    "binance-smart-chain": "binance-smart-chain",
    "bsc": "binance-smart-chain",
    "avalanche": "avalanche",
    "gnosis": "xdai",
    "fantom": "fantom",
    "celo": "celo",
    "linea": "linea",
    "zksync-era": "zksync",
    "scroll": "scroll",
    "blast": "blast",
    "mantle": "mantle",
    "mode": "mode",
    "sonic": "sonic",
}

# Native / gas token CoinGecko coin ids when there is no ERC-20 contract.
_COINGECKO_NATIVE_BY_SYMBOL: Dict[str, str] = {
    "ETH": "ethereum",
    "WETH": "weth",
    "BNB": "binancecoin",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "AVAX": "avalanche-2",
    "FTM": "fantom",
    "XDAI": "xdai",
    "DAI": "dai",
}

_STABLE_SYMBOLS = frozenset({"USDC", "USDT", "DAI", "USD", "USDC.E", "USDT.E"})

# Native-ish zero / sentinel addresses used across EVM chains.
_NATIVE_CONTRACTS = frozenset(
    {
        "",
        "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "0x0000000000000000000000000000000000000000",
    }
)


def _parse_iso_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _quantity_float(quantity: Any) -> Optional[float]:
    if not isinstance(quantity, dict):
        return positive_finite(quantity)
    for key in ("float", "numeric"):
        if key in quantity and quantity.get(key) is not None:
            return positive_finite(quantity.get(key))
    return None


def _rel_id(relationships: Any, key: str) -> Optional[str]:
    if not isinstance(relationships, dict):
        return None
    node = relationships.get(key)
    if not isinstance(node, dict):
        return None
    data = node.get("data")
    if isinstance(data, dict):
        rid = data.get("id")
        return str(rid).strip() if rid is not None else None
    return None


def _parse_chain_ids(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


class ZerionConnector(BaseConnector):
    """Track an EVM wallet via Zerion portfolio / positions / transactions APIs."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.address = (config.get("address") or "").strip()
        hostname = (config.get("hostname") or "").strip().rstrip("/")
        self.api_base = hostname or _DEFAULT_API_BASE
        self.api_key = (config.get("api_key") or "").strip()
        self.chain_ids = _parse_chain_ids(config.get("chain_ids"))
        # symbol → preferred (chain_id, contract_address) for CoinGecko charts
        self._impl_by_symbol: Dict[str, Tuple[str, str]] = {}
        self._price_by_symbol: Dict[str, float] = {}
        self._tx_cache: Optional[List[Dict[str, Any]]] = None

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.api_key}:".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = self._auth_header()
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        absolute: bool = False,
    ) -> Any:
        if absolute or path.startswith("http"):
            url = path
        else:
            url = urljoin((base_url or self.api_base).rstrip("/") + "/", path.lstrip("/"))
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    headers=headers if headers is not None else self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise ConnectorFetchError(f"zerion HTTP {method} {path}: {exc}") from exc
        except ValueError as exc:
            raise ConnectorFetchError(f"zerion JSON {method} {path}: {exc}") from exc

    def _chain_filter_params(self) -> Dict[str, Any]:
        if not self.chain_ids:
            return {}
        return {"filter[chain_ids]": ",".join(self.chain_ids)}

    def _remember_impl(
        self,
        symbol: str,
        chain_id: Optional[str],
        implementations: Any,
        *,
        prefer_value: float = 0.0,
    ) -> None:
        sym = symbol.strip().upper()
        if not sym:
            return
        chain = (chain_id or "").strip()
        contract = ""
        if isinstance(implementations, list):
            # Prefer the implementation matching the position's chain.
            chosen = None
            for item in implementations:
                if not isinstance(item, dict):
                    continue
                item_chain = str(item.get("chain_id") or "").strip()
                if chain and item_chain == chain:
                    chosen = item
                    break
                if chosen is None:
                    chosen = item
            if isinstance(chosen, dict):
                contract = str(chosen.get("address") or "").strip().lower()
                if not chain:
                    chain = str(chosen.get("chain_id") or "").strip()
        existing = self._impl_by_symbol.get(sym)
        if existing is None or prefer_value > 0:
            self._impl_by_symbol[sym] = (chain, contract)

    def _parse_positions(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise ConnectorFetchError("zerion positions: unexpected response shape")

        balances: Dict[str, float] = {}
        best_value: Dict[str, float] = {}

        for item in data:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes") or {}
            if not isinstance(attrs, dict):
                continue
            # only_simple already excludes DeFi; keep a hard guard for protocol rows.
            position_type = attrs.get("position_type")
            if position_type is not None and position_type != "wallet":
                continue
            info = attrs.get("fungible_info") or {}
            if not isinstance(info, dict):
                continue
            symbol = str(info.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            qty = _quantity_float(attrs.get("quantity"))
            if qty is None:
                continue
            balances[symbol] = balances.get(symbol, 0.0) + qty
            price = positive_finite(attrs.get("price"))
            if price is not None:
                self._price_by_symbol[symbol] = price
            value = positive_finite(attrs.get("value")) or 0.0
            chain_id = _rel_id(item.get("relationships"), "chain")
            if value >= best_value.get(symbol, -1.0):
                best_value[symbol] = value
                self._remember_impl(
                    symbol,
                    chain_id,
                    info.get("implementations"),
                    prefer_value=value,
                )

        rows: List[Dict[str, Any]] = []
        for symbol, quantity in sorted(balances.items()):
            cleaned = positive_finite(quantity)
            if cleaned is None:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": cleaned,
                    "exchange": self.name,
                }
            )
        return rows

    async def fetch_balances(self) -> List[Dict]:
        """Fetch simple (non-DeFi) fungible balances across configured chains."""
        if not self.address:
            raise ConnectorFetchError("zerion balances: wallet address is required")
        if not self.api_key:
            raise ConnectorFetchError("zerion balances: api_key is required")
        params: Dict[str, Any] = {
            "currency": "usd",
            "filter[positions]": "only_simple",
            "filter[trash]": "only_non_trash",
            "sort": "value",
        }
        params.update(self._chain_filter_params())
        try:
            payload = self._request_json(
                "GET",
                f"v1/wallets/{self.address}/positions/",
                params=params,
            )
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(f"zerion balances: {exc}") from exc
        if not isinstance(payload, dict):
            raise ConnectorFetchError("zerion balances: unexpected response shape")
        if payload.get("errors"):
            raise ConnectorFetchError(f"zerion balances: {payload.get('errors')}")
        return self._parse_positions(payload)

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """USD prices cached from the last positions response (and stables = 1)."""
        out: Dict[str, float] = {}
        for symbol in symbols:
            sym = str(symbol).strip().upper()
            if not sym:
                continue
            if sym in _STABLE_SYMBOLS:
                out[sym] = 1.0
                continue
            price = self._price_by_symbol.get(sym)
            if price is not None:
                out[sym] = price
        missing = [
            str(s).strip().upper()
            for s in symbols
            if str(s).strip().upper() and str(s).strip().upper() not in out
        ]
        if missing and self.address and self.api_key:
            # Refresh positions once so prices exist even if balances were not just synced.
            try:
                await self.fetch_balances()
            except ConnectorFetchError:
                pass
            for sym in missing:
                if sym in _STABLE_SYMBOLS:
                    out[sym] = 1.0
                elif sym in self._price_by_symbol:
                    out[sym] = self._price_by_symbol[sym]
        return out

    def _tx_params(self, since_ms: Optional[int]) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "currency": "usd",
            "page[size]": str(_TX_PAGE_SIZE),
            "filter[trash]": "only_non_trash",
            # Focus on movements that can imply cost basis / disposal.
            "filter[operation_types]": "trade,receive,send,deposit,withdraw",
            "filter[asset_types]": "fungible",
        }
        params.update(self._chain_filter_params())
        if since_ms is not None:
            params["filter[min_mined_at]"] = str(int(since_ms))
        return params

    def _fetch_transactions(self, since_ms: Optional[int]) -> List[Dict[str, Any]]:
        if self._tx_cache is not None and since_ms is None:
            return self._tx_cache
        if not self.address:
            raise ConnectorFetchError("zerion orders: wallet address is required")
        if not self.api_key:
            raise ConnectorFetchError("zerion orders: api_key is required")

        collected: List[Dict[str, Any]] = []
        params = self._tx_params(since_ms)
        next_url: Optional[str] = None
        for page in range(_TX_MAX_PAGES):
            if next_url:
                payload = self._request_json("GET", next_url, absolute=True)
            else:
                payload = self._request_json(
                    "GET",
                    f"v1/wallets/{self.address}/transactions/",
                    params=params,
                )
            if not isinstance(payload, dict):
                break
            data = payload.get("data") or []
            if isinstance(data, list):
                collected.extend(item for item in data if isinstance(item, dict))
            links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
            nxt = links.get("next") if isinstance(links, dict) else None
            if not nxt or not isinstance(data, list) or len(data) < _TX_PAGE_SIZE:
                break
            next_url = str(nxt)
            if page == _TX_MAX_PAGES - 1:
                break
        if since_ms is None:
            self._tx_cache = collected
        return collected

    def _transfer_symbol(self, transfer: Dict[str, Any]) -> Optional[str]:
        info = transfer.get("fungible_info")
        if not isinstance(info, dict):
            return None
        symbol = str(info.get("symbol") or "").strip().upper()
        return symbol or None

    def _normalize_transfer_order(
        self,
        *,
        tx: Dict[str, Any],
        transfer: Dict[str, Any],
        side: str,
        base_symbol: str,
        index: int,
        since_ms: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        qty = _quantity_float(transfer.get("quantity"))
        if qty is None:
            return None
        price = positive_finite(transfer.get("price"))
        value = positive_finite(transfer.get("value"))
        if price is None and value is not None and qty:
            price = positive_finite(value / qty)
        if price is None and base_symbol in _STABLE_SYMBOLS:
            price = 1.0
        if price is None:
            return None

        attrs = tx.get("attributes") if isinstance(tx.get("attributes"), dict) else {}
        executed_at = _parse_iso_utc(attrs.get("mined_at"))
        if executed_at is None:
            executed_at = _parse_iso_utc(attrs.get("mined_at_block"))
        if executed_at is None:
            executed_at = datetime.utcnow()
        if since_ms is not None:
            trade_ms = int(executed_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if trade_ms < since_ms:
                return None

        tx_hash = str(attrs.get("hash") or tx.get("id") or "").strip()
        if not tx_hash:
            return None
        external_id = f"{tx_hash}:{side}:{base_symbol}:{index}"
        return {
            "external_order_id": external_id,
            "symbol": base_symbol,
            "type": side,
            "quantity": qty,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def _orders_from_transaction(
        self,
        tx: Dict[str, Any],
        *,
        base_symbol: str,
        since_ms: Optional[int],
    ) -> List[Dict[str, Any]]:
        attrs = tx.get("attributes") if isinstance(tx.get("attributes"), dict) else {}
        transfers = attrs.get("transfers") or []
        if not isinstance(transfers, list):
            return []

        relevant: List[Tuple[int, Dict[str, Any]]] = []
        for idx, transfer in enumerate(transfers):
            if not isinstance(transfer, dict):
                continue
            if transfer.get("nft_info") and not transfer.get("fungible_info"):
                continue
            symbol = self._transfer_symbol(transfer)
            if symbol != base_symbol:
                continue
            direction = str(transfer.get("direction") or "").strip().lower()
            if direction not in {"in", "out"}:
                continue
            relevant.append((idx, transfer))

        out: List[Dict[str, Any]] = []
        for idx, transfer in relevant:
            direction = str(transfer.get("direction") or "").strip().lower()
            side = "buy" if direction == "in" else "sell"
            # Remember implementation metadata from the transfer when missing.
            info = transfer.get("fungible_info") if isinstance(transfer.get("fungible_info"), dict) else {}
            chain_id = _rel_id(tx.get("relationships"), "chain")
            if info and base_symbol not in self._impl_by_symbol:
                self._remember_impl(base_symbol, chain_id, info.get("implementations"))
            row = self._normalize_transfer_order(
                tx=tx,
                transfer=transfer,
                side=side,
                base_symbol=base_symbol,
                index=idx,
                since_ms=since_ms,
            )
            if row:
                out.append(row)
        return out

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Derive buy/sell orders from Zerion wallet transfers for ``market_pair`` base."""
        base = market_pair.split("/")[0].strip().upper() if market_pair else ""
        if not base:
            return []
        if base in _STABLE_SYMBOLS:
            return []

        try:
            transactions = self._fetch_transactions(since_ms)
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(f"zerion orders for {market_pair}: {exc}") from exc

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for tx in transactions:
            for row in self._orders_from_transaction(
                tx, base_symbol=base, since_ms=since_ms
            ):
                ext = row["external_order_id"]
                if ext in seen:
                    continue
                seen.add(ext)
                out.append(row)
                if not paginate and len(out) >= max(limit, 1):
                    return out
        return out

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Async wrapper; scheduler uses ``fetch_orders_sync``."""
        if not symbol:
            return []
        if "/" in symbol:
            pairs = [symbol]
        else:
            pairs = [f"{symbol}/USDC", f"{symbol}/USDT"]
        orders: List[Dict] = []
        seen: set[str] = set()
        for pair in pairs:
            for row in self.fetch_orders_sync(pair, since_ms=None, paginate=True):
                ext = row.get("external_order_id")
                if ext and ext in seen:
                    continue
                if ext:
                    seen.add(str(ext))
                orders.append(row)
        return orders

    def _coingecko_chart_target(self, base: str) -> Tuple[str, Dict[str, str]]:
        """Return (path, params) for CoinGecko market_chart."""
        lookback_placeholder = True  # days filled by caller
        _ = lookback_placeholder
        impl = self._impl_by_symbol.get(base)
        if impl:
            chain_id, contract = impl
            platform = _COINGECKO_PLATFORM_BY_CHAIN.get(chain_id)
            if platform and contract and contract not in _NATIVE_CONTRACTS:
                return (
                    f"coins/{platform}/contract/{contract}/market_chart",
                    {"vs_currency": "usd"},
                )
        native_id = _COINGECKO_NATIVE_BY_SYMBOL.get(base)
        if native_id:
            return (f"coins/{native_id}/market_chart", {"vs_currency": "usd"})
        raise ConnectorFetchError(f"zerion price history: unknown CoinGecko target for {base}")

    def fetch_price_history_sync(
        self,
        market_pair: str,
        since_ms: int,
        *,
        days: int,
    ) -> List[Dict[str, Any]]:
        """CoinGecko market chart for the EVM token (USD)."""
        base = market_pair.split("/")[0].strip().upper() if market_pair else ""
        if not base:
            return []
        lookback_days = max(1, int(days))
        path, params = self._coingecko_chart_target(base)
        params = {**params, "days": str(lookback_days)}

        try:
            payload = self._request_json(
                "GET",
                path,
                params=params,
                base_url=_COINGECKO_API_BASE,
                headers={"Accept": "application/json"},
            )
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(
                f"zerion CoinGecko history for {market_pair}: {exc}"
            ) from exc

        prices = payload.get("prices") if isinstance(payload, dict) else None
        if not isinstance(prices, list):
            return []

        points: List[Dict[str, Any]] = []
        seen_ts: set[int] = set()
        for entry in prices:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            try:
                ts_ms = int(entry[0])
                close = float(entry[1])
            except (TypeError, ValueError):
                continue
            if ts_ms < since_ms or ts_ms in seen_ts:
                continue
            if positive_finite(close) is None:
                continue
            seen_ts.add(ts_ms)
            ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            points.append(
                {
                    "timestamp": ts,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "price": close,
                }
            )
        return points

    async def test_connection(self) -> bool:
        """Require address + API key and a reachable portfolio endpoint."""
        if not self.address or not self.api_key:
            return False
        try:
            params: Dict[str, Any] = {
                "currency": "usd",
                "filter[positions]": "only_simple",
            }
            params.update(self._chain_filter_params())
            payload = self._request_json(
                "GET",
                f"v1/wallets/{self.address}/portfolio",
                params=params,
            )
        except ConnectorFetchError:
            return False
        return isinstance(payload, dict) and "errors" not in payload
