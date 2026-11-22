"""Jupiter Solana wallet connector (Ultra holdings + Trigger orders + Price API)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import httpx

from ..utils.data_quality import ConnectorFetchError, positive_finite
from .base import BaseConnector

# Native / wrapped SOL and common USD stables on Solana.
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
_STABLE_MINTS = frozenset({USDC_MINT, USDT_MINT})

_DEFAULT_API_BASE = "https://api.jup.ag"
_COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
_PRICE_BATCH_SIZE = 50
_SEARCH_BATCH_SIZE = 100
_TRIGGER_PAGE_SIZE = 10  # Jupiter Trigger V1 pages ~10 orders
_TRIGGER_MAX_PAGES = 50
_HTTP_TIMEOUT = 30.0


def _parse_iso_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Trigger V2 uses unix seconds; V1 history uses ISO strings.
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


def _ui_amount(entry: Dict[str, Any]) -> Optional[float]:
    if "uiAmount" in entry and entry.get("uiAmount") is not None:
        return positive_finite(entry.get("uiAmount"))
    amount = entry.get("amount")
    decimals = entry.get("decimals")
    if amount is None or decimals is None:
        return None
    try:
        raw = float(amount)
        places = int(decimals)
    except (TypeError, ValueError):
        return None
    return positive_finite(raw / (10**places))


class JupiterConnector(BaseConnector):
    """Track a Solana wallet via Jupiter Ultra / Trigger / Price APIs."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.address = (config.get("address") or "").strip()
        hostname = (config.get("hostname") or "").strip().rstrip("/")
        self.api_base = hostname or _DEFAULT_API_BASE
        self.api_key = (config.get("api_key") or "").strip()
        # Mint ↔ ticker maps filled during balance / metadata sync.
        self._mint_by_symbol: Dict[str, str] = {"SOL": SOL_MINT}
        self._symbol_by_mint: Dict[str, str] = {SOL_MINT: "SOL"}
        self._decimals_by_mint: Dict[str, int] = {SOL_MINT: 9}

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.api_base.rstrip("/") + "/", path.lstrip("/"))

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = (
            urljoin((base_url or self.api_base).rstrip("/") + "/", path.lstrip("/"))
            if not path.startswith("http")
            else path
        )
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
            raise ConnectorFetchError(f"jupiter HTTP {method} {path}: {exc}") from exc
        except ValueError as exc:
            raise ConnectorFetchError(f"jupiter JSON {method} {path}: {exc}") from exc

    def _remember_token(self, mint: str, symbol: str, decimals: Optional[int] = None) -> str:
        clean_symbol = (symbol or "").strip().upper() or mint[:6]
        # Prefer the first non-empty ticker we see for a mint.
        existing = self._symbol_by_mint.get(mint)
        if existing and existing != mint[:6]:
            clean_symbol = existing
        else:
            self._symbol_by_mint[mint] = clean_symbol
        self._mint_by_symbol.setdefault(clean_symbol, mint)
        if decimals is not None:
            try:
                self._decimals_by_mint[mint] = int(decimals)
            except (TypeError, ValueError):
                pass
        return clean_symbol

    def _search_tokens(self, queries: Iterable[str]) -> List[Dict[str, Any]]:
        """Resolve mints/symbols via Token API search (Ultra or Tokens V2)."""
        unique = [q for q in dict.fromkeys(q.strip() for q in queries if q and str(q).strip())]
        if not unique:
            return []
        results: List[Dict[str, Any]] = []
        for i in range(0, len(unique), _SEARCH_BATCH_SIZE):
            chunk = unique[i : i + _SEARCH_BATCH_SIZE]
            query = ",".join(chunk)
            # Prefer Tokens V2; fall back to Ultra search for the same query shape.
            for path in ("tokens/v2/search", "ultra/v1/search"):
                try:
                    payload = self._request_json("GET", path, params={"query": query})
                except ConnectorFetchError:
                    continue
                if isinstance(payload, list):
                    results.extend(item for item in payload if isinstance(item, dict))
                    break
                if isinstance(payload, dict):
                    nested = payload.get("tokens") or payload.get("data") or []
                    if isinstance(nested, list):
                        results.extend(item for item in nested if isinstance(item, dict))
                        break
        return results

    def _hydrate_metadata(self, mints: List[str]) -> None:
        unknown = [m for m in mints if m and m not in self._symbol_by_mint]
        if not unknown:
            return
        for item in self._search_tokens(unknown):
            mint = str(item.get("id") or item.get("address") or item.get("mint") or "").strip()
            if not mint:
                continue
            symbol = str(item.get("symbol") or "").strip()
            decimals = item.get("decimals")
            self._remember_token(mint, symbol, decimals if decimals is not None else None)

        for mint in unknown:
            self._symbol_by_mint.setdefault(mint, mint[:6].upper())
            self._mint_by_symbol.setdefault(self._symbol_by_mint[mint], mint)

    def _parse_holdings(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        mint_qty: Dict[str, float] = {}

        # Top-level fields are native SOL (lamports / uiAmount).
        sol_qty = _ui_amount(payload) if isinstance(payload, dict) else None
        if sol_qty is not None:
            mint_qty[SOL_MINT] = mint_qty.get(SOL_MINT, 0.0) + sol_qty
            self._remember_token(SOL_MINT, "SOL", 9)

        tokens = payload.get("tokens") if isinstance(payload, dict) else None
        if isinstance(tokens, dict):
            for mint, accounts in tokens.items():
                mint_s = str(mint).strip()
                if not mint_s or not isinstance(accounts, list):
                    continue
                total = 0.0
                decimals: Optional[int] = None
                for account in accounts:
                    if not isinstance(account, dict):
                        continue
                    if account.get("excludeFromNetWorth") is True:
                        continue
                    qty = _ui_amount(account)
                    if qty is None:
                        continue
                    total += qty
                    if decimals is None and account.get("decimals") is not None:
                        try:
                            decimals = int(account["decimals"])
                        except (TypeError, ValueError):
                            decimals = None
                if total <= 0:
                    continue
                mint_qty[mint_s] = mint_qty.get(mint_s, 0.0) + total
                if decimals is not None:
                    self._decimals_by_mint[mint_s] = decimals

        self._hydrate_metadata(list(mint_qty.keys()))

        balances: Dict[str, float] = {}
        for mint, qty in mint_qty.items():
            symbol = self._symbol_by_mint.get(mint, mint[:6].upper())
            # Fold wrapped SOL into native SOL ticker.
            if mint == SOL_MINT:
                symbol = "SOL"
            balances[symbol] = balances.get(symbol, 0.0) + qty
            self._mint_by_symbol.setdefault(symbol, mint)

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
        """Fetch SOL + SPL token balances for the configured wallet."""
        if not self.address:
            raise ConnectorFetchError("jupiter balances: wallet address is required")
        try:
            payload = self._request_json("GET", f"ultra/v1/holdings/{self.address}")
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(f"jupiter balances: {exc}") from exc
        if not isinstance(payload, dict):
            raise ConnectorFetchError("jupiter balances: unexpected response shape")
        if payload.get("error"):
            raise ConnectorFetchError(f"jupiter balances: {payload.get('error')}")
        return self._parse_holdings(payload)

    def _price_by_mints(self, mints: List[str]) -> Dict[str, float]:
        unique = [m for m in dict.fromkeys(mints) if m]
        prices: Dict[str, float] = {}
        for i in range(0, len(unique), _PRICE_BATCH_SIZE):
            chunk = unique[i : i + _PRICE_BATCH_SIZE]
            payload = self._request_json(
                "GET",
                "price/v3",
                params={"ids": ",".join(chunk)},
            )
            if not isinstance(payload, dict):
                continue
            for mint, info in payload.items():
                if not isinstance(info, dict):
                    continue
                usd = positive_finite(info.get("usdPrice"))
                if usd is not None:
                    prices[str(mint)] = usd
        # Fill gaps from Token search usdPrice when Price API omits a mint.
        missing = [m for m in unique if m not in prices]
        if missing:
            for item in self._search_tokens(missing):
                mint = str(item.get("id") or item.get("address") or "").strip()
                usd = positive_finite(item.get("usdPrice"))
                if mint and usd is not None:
                    prices[mint] = usd
                    symbol = str(item.get("symbol") or "").strip()
                    if symbol:
                        self._remember_token(mint, symbol, item.get("decimals"))
        return prices

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """USD prices for held tickers via Jupiter Price API (mint ids)."""
        if not symbols:
            return {}
        mints: List[str] = []
        symbol_for_mint: Dict[str, str] = {}
        unresolved: List[str] = []
        for symbol in symbols:
            sym = str(symbol).strip().upper()
            if not sym:
                continue
            mint = self._mint_by_symbol.get(sym)
            if mint:
                mints.append(mint)
                symbol_for_mint[mint] = sym
            else:
                unresolved.append(sym)
        if unresolved:
            for item in self._search_tokens(unresolved):
                mint = str(item.get("id") or item.get("address") or "").strip()
                symbol = str(item.get("symbol") or "").strip().upper()
                if not mint or not symbol:
                    continue
                self._remember_token(mint, symbol, item.get("decimals"))
                if symbol in unresolved:
                    mints.append(mint)
                    symbol_for_mint[mint] = symbol
        try:
            by_mint = self._price_by_mints(mints)
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(f"jupiter prices: {exc}") from exc
        out: Dict[str, float] = {}
        for mint, price in by_mint.items():
            symbol = symbol_for_mint.get(mint) or self._symbol_by_mint.get(mint)
            if symbol:
                out[symbol] = price
        return out

    def _sol_usd_price(self) -> float:
        prices = self._price_by_mints([SOL_MINT])
        usd = prices.get(SOL_MINT)
        if usd is None:
            raise ConnectorFetchError("jupiter: missing SOL USD price")
        return usd

    def _mint_for_symbol(self, symbol: str) -> Optional[str]:
        sym = symbol.strip().upper()
        if not sym:
            return None
        if sym in self._mint_by_symbol:
            return self._mint_by_symbol[sym]
        for item in self._search_tokens([sym]):
            mint = str(item.get("id") or item.get("address") or "").strip()
            ticker = str(item.get("symbol") or "").strip().upper()
            if mint and ticker == sym:
                self._remember_token(mint, ticker, item.get("decimals"))
                return mint
        return None

    def _normalize_trade(
        self,
        trade: Dict[str, Any],
        *,
        base_mint: str,
        base_symbol: str,
        sol_usd: float,
        since_ms: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        action = str(trade.get("action") or "").strip().lower()
        if action and action not in {"fill", "filled"}:
            return None
        input_mint = str(trade.get("inputMint") or "").strip()
        output_mint = str(trade.get("outputMint") or "").strip()
        if base_mint not in {input_mint, output_mint}:
            return None

        executed_at = _parse_iso_utc(trade.get("confirmedAt"))
        if executed_at is None:
            executed_at = datetime.utcnow()
        if since_ms is not None:
            trade_ms = int(executed_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if trade_ms < since_ms:
                return None

        try:
            input_amount = float(trade.get("inputAmount") or 0)
            output_amount = float(trade.get("outputAmount") or 0)
        except (TypeError, ValueError):
            return None

        if output_mint == base_mint:
            side = "buy"
            quantity = output_amount
            quote_amount, quote_mint = input_amount, input_mint
        else:
            side = "sell"
            quantity = input_amount
            quote_amount, quote_mint = output_amount, output_mint

        qty = positive_finite(quantity)
        if qty is None:
            return None

        if quote_mint in _STABLE_MINTS:
            usd_total = quote_amount
        elif quote_mint == SOL_MINT:
            usd_total = quote_amount * sol_usd
        else:
            # Rare non-SOL/stable quote: price the quote mint and convert.
            quote_prices = self._price_by_mints([quote_mint])
            quote_usd = quote_prices.get(quote_mint)
            if quote_usd is None:
                return None
            usd_total = quote_amount * quote_usd

        price = positive_finite(usd_total / qty) if qty else None
        if price is None:
            return None

        tx_id = trade.get("txId") or trade.get("signature")
        order_key = trade.get("orderKey")
        if tx_id:
            external_id = f"{tx_id}:{base_symbol}:{side}"
        elif order_key:
            external_id = f"{order_key}:{side}:{executed_at.isoformat()}"
        else:
            return None

        return {
            "external_order_id": external_id,
            "symbol": base_symbol,
            "type": side,
            "quantity": qty,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def _fetch_trigger_history_pages(self) -> List[Dict[str, Any]]:
        """Trigger V1 history for an arbitrary wallet (user= query param).

        Trigger V2 `/orders/history` is scoped to the authenticated wallet only,
        so V1 is required when tracking a configured public address.
        """
        if not self.address:
            raise ConnectorFetchError("jupiter orders: wallet address is required")
        collected: List[Dict[str, Any]] = []
        for page in range(1, _TRIGGER_MAX_PAGES + 1):
            payload = self._request_json(
                "GET",
                "trigger/v1/getTriggerOrders",
                params={
                    "user": self.address,
                    "orderStatus": "history",
                    "page": str(page),
                },
            )
            if not isinstance(payload, dict):
                break
            orders = payload.get("orders") or []
            if not isinstance(orders, list):
                break
            collected.extend(o for o in orders if isinstance(o, dict))
            total_pages = payload.get("totalPages")
            try:
                total_pages_i = int(total_pages) if total_pages is not None else page
            except (TypeError, ValueError):
                total_pages_i = page
            if page >= total_pages_i or len(orders) < _TRIGGER_PAGE_SIZE:
                break
        return collected

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Executed Trigger fills for the base of ``market_pair`` (USD prices)."""
        base = market_pair.split("/")[0].strip().upper() if market_pair else ""
        if not base:
            return []
        # Stablecoin "positions" are not reconstructed from Jupiter trigger fills.
        if base in {"USDC", "USDT", "USD"}:
            return []

        base_mint = self._mint_for_symbol(base)
        if not base_mint:
            print(f"jupiter orders: could not resolve mint for {base}")
            return []

        try:
            sol_usd = self._sol_usd_price()
            raw_orders = self._fetch_trigger_history_pages()
        except ConnectorFetchError:
            raise
        except Exception as exc:
            raise ConnectorFetchError(f"jupiter orders for {market_pair}: {exc}") from exc

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for order in raw_orders:
            status = str(order.get("status") or "").strip().lower()
            # Keep completed / partial history; skip cancelled with no fills.
            trades = order.get("trades") or []
            if not isinstance(trades, list):
                continue
            if status in {"cancelled", "canceled", "expired"} and not trades:
                continue
            for trade in trades:
                if not isinstance(trade, dict):
                    continue
                row = self._normalize_trade(
                    trade,
                    base_mint=base_mint,
                    base_symbol=base,
                    sol_usd=sol_usd,
                    since_ms=since_ms,
                )
                if not row:
                    continue
                ext = row["external_order_id"]
                if ext in seen:
                    continue
                seen.add(ext)
                out.append(row)
                if not paginate and len(out) >= max(limit, 1):
                    return out
        return out

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Async wrapper used by ad-hoc callers; scheduler uses fetch_orders_sync."""
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

    def fetch_price_history_sync(
        self,
        market_pair: str,
        since_ms: int,
        *,
        days: int,
    ) -> List[Dict[str, Any]]:
        """CoinGecko market chart for Solana tokens (USD)."""
        base = market_pair.split("/")[0].strip().upper() if market_pair else ""
        if not base:
            return []
        mint = self._mint_for_symbol(base)
        lookback_days = max(1, int(days))

        if base == "SOL" or mint == SOL_MINT:
            path = "coins/solana/market_chart"
            params = {"vs_currency": "usd", "days": str(lookback_days)}
        else:
            if not mint:
                raise ConnectorFetchError(
                    f"jupiter price history: unknown mint for {base}"
                )
            path = f"coins/solana/contract/{mint}/market_chart"
            params = {"vs_currency": "usd", "days": str(lookback_days)}

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
                f"jupiter CoinGecko history for {market_pair}: {exc}"
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
        """Require a wallet address and a reachable Jupiter holdings endpoint."""
        if not self.address:
            return False
        try:
            payload = self._request_json("GET", f"ultra/v1/holdings/{self.address}")
        except ConnectorFetchError:
            return False
        return isinstance(payload, dict) and "error" not in payload
