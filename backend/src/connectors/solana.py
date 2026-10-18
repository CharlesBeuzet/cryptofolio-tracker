"""Solana wallet connector (Helius RPC).

Balances come from one DAS ``getAssetsByOwner`` call. Orders are conversions
against USDT or USDC only: the execution price is the stablecoin amount
divided by the token amount in the same transaction. Transfers, airdrops, and
swaps that are not against those quotes are ignored. Market prices are out of
scope (``fetch_prices`` stays empty).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from ..utils.data_quality import VALUE_EPSILON, ConnectorFetchError, positive_finite
from .base import BaseConnector

# Wrapped SOL and the quote mints that match QUOTE_CURRENCIES.
WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
QUOTE_MINTS = {USDC_MINT: "USDC", USDT_MINT: "USDT"}
# Keep aligned with services.orders.QUOTE_CURRENCIES (USDT, USDC).
QUOTE_SYMBOLS = tuple(QUOTE_MINTS.values())
CANONICAL_MINTS = {WSOL_MINT: "SOL", **QUOTE_MINTS}

ASSET_PAGE_LIMIT = 1000
ASSET_MAX_PAGES = 10
TX_PAGE_LIMIT = 1000
TX_MAX_PAGES = 25
# Account-rent left beside a token/stable swap is not a third traded asset.
RENT_TOLERANCE_LAMPORTS = 20_000_000  # 0.02 SOL
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
SYMBOL_MAX_LEN = 20

Transport = Callable[[str, Any], Any]


def _decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, Decimal):
        return value
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return number


def _clean_symbol(raw: Any) -> str:
    text = "".join(ch for ch in str(raw or "").upper() if ch.isalnum())
    return text[:SYMBOL_MAX_LEN]


def _with_suffix(symbol: str, mint: str) -> str:
    suffix = "." + (mint[-4:] if mint else "XXXX")
    room = SYMBOL_MAX_LEN - len(suffix)
    base = (symbol or "TOKEN")[: max(room, 1)]
    fitted = f"{base}{suffix}"
    return fitted[:SYMBOL_MAX_LEN]


def _ui_amount(entry: Dict[str, Any]) -> Decimal:
    ui = entry.get("uiTokenAmount") or {}
    parsed = _decimal(ui.get("uiAmountString"))
    if parsed is not None:
        return parsed
    amount = _decimal(ui.get("amount"))
    decimals = ui.get("decimals") or 0
    if amount is None:
        return Decimal(0)
    try:
        scale = Decimal(10) ** int(decimals)
    except (TypeError, ValueError):
        return Decimal(0)
    if scale == 0:
        return Decimal(0)
    return amount / scale


def _token_totals(rows: Optional[List[Dict[str, Any]]], wallet: str) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("owner") != wallet:
            continue
        mint = row.get("mint")
        if not mint:
            continue
        totals[str(mint)] = totals.get(str(mint), Decimal(0)) + _ui_amount(row)
    return totals


def _account_keys(transaction: Dict[str, Any], meta: Dict[str, Any]) -> List[str]:
    message = (transaction or {}).get("message") or {}
    keys: List[str] = []
    for key in message.get("accountKeys") or []:
        if isinstance(key, str):
            keys.append(key)
        elif isinstance(key, dict):
            keys.append(str(key.get("pubkey") or ""))
    loaded = meta.get("loadedAddresses") or {}
    keys.extend(str(item) for item in (loaded.get("writable") or []))
    keys.extend(str(item) for item in (loaded.get("readonly") or []))
    return keys


def _is_fungible(item: Dict[str, Any]) -> bool:
    if item.get("burnt"):
        return False
    interface = str(item.get("interface") or "")
    upper = interface.upper()
    if "NFT" in upper or upper in {"V1_PRINT", "PROGRAMMABLENFT"}:
        return False
    info = item.get("token_info")
    if not isinstance(info, dict) or "balance" not in info:
        return False
    if upper.startswith("FUNGIBLE"):
        return True
    supply = info.get("supply")
    if supply is None:
        return info.get("decimals") is not None
    try:
        return int(supply) > 1
    except (TypeError, ValueError):
        return False


def _raw_balance(info: Dict[str, Any]) -> Optional[Decimal]:
    balance = _decimal(info.get("balance"))
    if balance is None or balance <= 0:
        return None
    decimals = info.get("decimals")
    if decimals is None:
        return None
    try:
        scale = Decimal(10) ** int(decimals)
    except (TypeError, ValueError):
        return None
    if scale == 0:
        return None
    return balance / scale


class SolanaConnector(BaseConnector):
    """Helius-backed connector for one Solana wallet."""

    def __init__(self, config: Dict, transport: Optional[Transport] = None):
        super().__init__(config)
        self.hostname = (config.get("hostname") or "").strip()
        self.address = (config.get("address") or "").strip()
        self.api_key = (config.get("api_key") or "").strip()
        self._transport = transport
        self._symbols_by_mint: Dict[str, str] = dict(CANONICAL_MINTS)
        self._index_loaded = False
        self._history_cache: Optional[Dict[str, Any]] = None

    def syncs_per_market_pair(self) -> bool:
        return False

    def full_history_when_empty(self) -> bool:
        return True

    def _require_config(self) -> None:
        if not self.address or not self.hostname or not self.api_key:
            raise ConnectorFetchError(
                "solana: address, hostname, and api_key are required"
            )

    def _endpoint(self) -> str:
        parts = urlsplit(self.hostname)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if "api-key" not in query:
            query["api-key"] = self.api_key
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _rpc(self, method: str, params: Any) -> Any:
        self._require_config()
        if self._transport is not None:
            try:
                return self._transport(method, params)
            except ConnectorFetchError:
                raise
            except Exception as exc:
                raise ConnectorFetchError(
                    f"solana {method}: {type(exc).__name__}"
                ) from exc

        payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}
        try:
            response = httpx.post(self._endpoint(), json=payload, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise ConnectorFetchError(f"solana {method}: {type(exc).__name__}") from exc
        if not isinstance(body, dict):
            raise ConnectorFetchError(f"solana {method}: response was not an object")
        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            if method == "getAssetsByOwner" and "no assets" in str(message).lower():
                return {"items": [], "nativeBalance": {"lamports": 0}}
            raise ConnectorFetchError(f"solana {method}: {message}")
        if "result" not in body:
            raise ConnectorFetchError(f"solana {method}: missing result")
        return body["result"]

    async def fetch_balances(self) -> List[Dict]:
        return await asyncio.to_thread(self._fetch_balances_sync)

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        rows = await asyncio.to_thread(
            self.fetch_orders_sync, symbol or "", None, paginate=True
        )
        return rows

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Market prices are provided by exchange connectors, not this wallet."""
        return {}

    async def test_connection(self) -> bool:
        if not self.address or not self.hostname or not self.api_key:
            return False
        try:
            self._rpc(
                "getAssetsByOwner",
                {
                    "ownerAddress": self.address,
                    "page": 1,
                    "limit": 1,
                    "options": {"showFungible": True, "showNativeBalance": True},
                },
            )
        except ConnectorFetchError:
            return False
        return True

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        symbol = (market_pair or "").split("/")[0].strip()
        rows = self._cached_conversions(since_ms, paginate=paginate, limit=limit)
        if not symbol:
            return rows
        return [row for row in rows if row["symbol"] == symbol]

    def _fetch_balances_sync(self) -> List[Dict]:
        """Page ``getAssetsByOwner`` and remember mint → symbol for later swaps."""
        holdings: Dict[str, Decimal] = {}
        labels: Dict[str, str] = {}
        native_lamports = 0
        page = 1
        while page <= ASSET_MAX_PAGES:
            result = self._rpc(
                "getAssetsByOwner",
                {
                    "ownerAddress": self.address,
                    "page": page,
                    "limit": ASSET_PAGE_LIMIT,
                    "options": {
                        "showFungible": True,
                        "showNativeBalance": True,
                        "showZeroBalance": False,
                    },
                },
            )
            if not isinstance(result, dict):
                raise ConnectorFetchError("solana getAssetsByOwner: result was not an object")
            if page == 1:
                native = result.get("nativeBalance") or {}
                parsed = _decimal(native.get("lamports"))
                native_lamports = int(parsed) if parsed is not None and parsed > 0 else 0
            items = result.get("items") or []
            if not isinstance(items, list):
                raise ConnectorFetchError("solana getAssetsByOwner: items was not a list")
            for item in items:
                if not isinstance(item, dict) or not _is_fungible(item):
                    continue
                mint = str(item.get("id") or "")
                info = item.get("token_info") or {}
                quantity = _raw_balance(info)
                if not mint or quantity is None:
                    continue
                holdings[mint] = holdings.get(mint, Decimal(0)) + quantity
                metadata = ((item.get("content") or {}).get("metadata") or {})
                labels[mint] = _clean_symbol(info.get("symbol") or metadata.get("symbol"))
            if len(items) < ASSET_PAGE_LIMIT:
                break
            page += 1

        if native_lamports:
            holdings["native"] = Decimal(native_lamports) / LAMPORTS_PER_SOL
            labels["native"] = "SOL"
        wsol = holdings.pop(WSOL_MINT, None)
        if wsol is not None:
            holdings["native"] = holdings.get("native", Decimal(0)) + wsol
            labels["native"] = "SOL"

        rows = self._rows_from_holdings(holdings, labels)
        self._symbols_by_mint = dict(CANONICAL_MINTS)
        for row in rows:
            mint = row.pop("_mint")
            if mint != "native":
                self._symbols_by_mint[mint] = row["symbol"]
        self._index_loaded = True
        return rows

    def _rows_from_holdings(
        self, holdings: Dict[str, Decimal], labels: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        drafted: List[Dict[str, Any]] = []
        for mint, quantity in holdings.items():
            if quantity <= Decimal(str(VALUE_EPSILON)):
                continue
            symbol = CANONICAL_MINTS.get(mint) or labels.get(mint) or ""
            if mint == "native":
                symbol = "SOL"
            if not symbol:
                symbol = "TOKEN"
            drafted.append({"_mint": mint, "symbol": symbol, "quantity": quantity})

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in drafted:
            grouped.setdefault(row["symbol"], []).append(row)

        balances: List[Dict[str, Any]] = []
        for symbol, group in grouped.items():
            if len(group) == 1:
                group[0]["symbol"] = symbol[:SYMBOL_MAX_LEN]
                continue
            bare = [
                row
                for row in group
                if CANONICAL_MINTS.get(row["_mint"]) == symbol or row["_mint"] == "native"
            ]
            for row in group:
                if row in bare:
                    row["symbol"] = symbol[:SYMBOL_MAX_LEN]
                else:
                    row["symbol"] = _with_suffix(symbol, row["_mint"])
        seen: Dict[str, Decimal] = {}
        order: List[str] = []
        mint_for: Dict[str, str] = {}
        for row in drafted:
            symbol = row["symbol"]
            if symbol not in seen:
                order.append(symbol)
                mint_for[symbol] = row["_mint"]
            seen[symbol] = seen.get(symbol, Decimal(0)) + row["quantity"]
        for symbol in order:
            quantity = positive_finite(seen[symbol])
            if quantity is None:
                continue
            balances.append(
                {
                    "_mint": mint_for[symbol],
                    "symbol": symbol,
                    "quantity": quantity,
                    "exchange": self.name,
                }
            )
        return balances

    def _cached_conversions(
        self, since_ms: Optional[int], *, paginate: bool, limit: int
    ) -> List[Dict[str, Any]]:
        cached = self._history_cache
        if cached and _cache_covers(cached, since_ms, paginate):
            return _within_since(cached["rows"], since_ms)
        if not self._index_loaded:
            self._fetch_balances_sync()
        rows = self._fetch_conversions(since_ms, paginate=paginate, limit=limit)
        self._history_cache = {"since_ms": since_ms, "paginate": paginate, "rows": rows}
        return rows

    def _fetch_conversions(
        self, since_ms: Optional[int], *, paginate: bool, limit: int
    ) -> List[Dict[str, Any]]:
        page_limit = TX_PAGE_LIMIT if paginate else max(1, min(int(limit or 1), TX_PAGE_LIMIT))
        since_seconds = None if since_ms is None else int(since_ms) // 1000
        pagination: Optional[str] = None
        found: List[Dict[str, Any]] = []
        pages = TX_MAX_PAGES if paginate else 1
        for _ in range(pages):
            config: Dict[str, Any] = {
                "transactionDetails": "full",
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 1,
                "sortOrder": "desc",
                "commitment": "finalized",
                "limit": page_limit,
                "filters": {
                    "status": "succeeded",
                    "tokenAccounts": "balanceChanged",
                },
            }
            if since_seconds is not None:
                config["filters"]["blockTime"] = {"gte": since_seconds}
            if pagination:
                config["paginationToken"] = pagination
            result = self._rpc("getTransactionsForAddress", [self.address, config])
            if not isinstance(result, dict):
                raise ConnectorFetchError(
                    "solana getTransactionsForAddress: result was not an object"
                )
            data = result.get("data") or []
            if not isinstance(data, list):
                raise ConnectorFetchError(
                    "solana getTransactionsForAddress: data was not a list"
                )
            stop = False
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                block_time = entry.get("blockTime")
                if since_seconds is not None and isinstance(block_time, int) and block_time < since_seconds:
                    stop = True
                    break
                row = self._conversion_row(entry)
                if row is not None:
                    found.append(row)
            token = result.get("paginationToken")
            if stop or not paginate or not token or not data:
                break
            pagination = str(token)
        return found

    def _conversion_row(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        block_time = entry.get("blockTime")
        if not isinstance(block_time, int):
            return None
        transaction = entry.get("transaction") or {}
        meta = entry.get("meta") or {}
        if meta.get("err"):
            return None
        signatures = transaction.get("signatures") or []
        if not signatures:
            return None
        signature = str(signatures[0])
        deltas = self._deltas_by_symbol(transaction, meta)
        priced = _stable_conversion(deltas)
        if priced is None:
            return None
        symbol, side, quantity, price = priced
        executed_at = datetime.fromtimestamp(block_time, tz=timezone.utc).replace(tzinfo=None)
        return {
            "external_order_id": f"{signature}:{symbol}",
            "symbol": symbol,
            "type": side,
            "quantity": quantity,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def _deltas_by_symbol(
        self, transaction: Dict[str, Any], meta: Dict[str, Any]
    ) -> Dict[str, Decimal]:
        deltas: Dict[str, Decimal] = {}
        sol = _sol_delta(transaction, meta, self.address)
        if sol is not None and abs(sol) > Decimal(str(VALUE_EPSILON)):
            deltas["SOL"] = sol
        pre = _token_totals(meta.get("preTokenBalances"), self.address)
        post = _token_totals(meta.get("postTokenBalances"), self.address)
        for mint in set(pre) | set(post):
            change = post.get(mint, Decimal(0)) - pre.get(mint, Decimal(0))
            if abs(change) <= Decimal(str(VALUE_EPSILON)):
                continue
            if mint == WSOL_MINT:
                symbol = "SOL"
            elif mint in QUOTE_MINTS:
                symbol = QUOTE_MINTS[mint]
            else:
                symbol = self._symbols_by_mint.get(mint) or f"mint:{mint}"
            deltas[symbol] = deltas.get(symbol, Decimal(0)) + change
        return {
            symbol: amount
            for symbol, amount in deltas.items()
            if abs(amount) > Decimal(str(VALUE_EPSILON))
        }


def _sol_delta(
    transaction: Dict[str, Any], meta: Dict[str, Any], wallet: str
) -> Optional[Decimal]:
    keys = _account_keys(transaction, meta)
    try:
        index = keys.index(wallet)
    except ValueError:
        return None
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if index >= len(pre) or index >= len(post):
        return None
    try:
        delta = int(post[index]) - int(pre[index])
    except (TypeError, ValueError):
        return None
    if keys and keys[0] == wallet:
        try:
            delta += int(meta.get("fee") or 0)
        except (TypeError, ValueError):
            pass
    if abs(delta) <= 1:
        return None
    return Decimal(delta) / LAMPORTS_PER_SOL


def _stable_conversion(
    deltas: Dict[str, Decimal],
) -> Optional[Tuple[str, str, float, float]]:
    """Return (symbol, side, quantity, price) for one token against one stable."""
    quotes = {symbol: amount for symbol, amount in deltas.items() if symbol in QUOTE_SYMBOLS}
    bases = {symbol: amount for symbol, amount in deltas.items() if symbol not in QUOTE_SYMBOLS}
    if len(quotes) != 1:
        return None
    sol = bases.get("SOL")
    if sol is not None and len(bases) == 2:
        other = [symbol for symbol in bases if symbol != "SOL"][0]
        if abs(sol) * LAMPORTS_PER_SOL <= RENT_TOLERANCE_LAMPORTS and not other.startswith("mint:"):
            bases = {other: bases[other]}
    if len(bases) != 1:
        return None
    symbol, token_delta = next(iter(bases.items()))
    if symbol.startswith("mint:"):
        return None
    quote_delta = next(iter(quotes.values()))
    if token_delta == 0 or quote_delta == 0 or (token_delta > 0) == (quote_delta > 0):
        return None
    quantity = positive_finite(abs(token_delta))
    price = positive_finite(abs(quote_delta) / abs(token_delta))
    if quantity is None or price is None:
        return None
    side = "buy" if token_delta > 0 else "sell"
    return symbol, side, quantity, price


def _cache_covers(cached: Dict[str, Any], since_ms: Optional[int], paginate: bool) -> bool:
    if paginate and not cached["paginate"]:
        return False
    cached_since = cached["since_ms"]
    if since_ms is None:
        return cached_since is None
    if cached_since is None:
        return True
    return int(cached_since) <= int(since_ms)


def _within_since(rows: List[Dict[str, Any]], since_ms: Optional[int]) -> List[Dict[str, Any]]:
    if since_ms is None:
        return list(rows)
    cutoff = datetime.fromtimestamp(int(since_ms) / 1000.0, tz=timezone.utc).replace(tzinfo=None)
    return [row for row in rows if row["executed_at"] >= cutoff]
