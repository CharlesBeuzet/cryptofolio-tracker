"""Helius Wallet API connector for Solana on-chain holdings and transactions."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from .base import BaseConnector
from .coingecko_client import CoinGeckoClient

_BASE_URL = "https://api.helius.xyz"
_SOL_MINT = "So11111111111111111111111111111111111111112"
_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
_QUOTE_MINTS = {_SOL_MINT, _USDC_MINT, _USDT_MINT}
_COLD_START_DAYS = 730
_HISTORY_PAGE_LIMIT = 100
_BALANCE_PAGE_LIMIT = 100


class HeliusConnector(BaseConnector):
    """Fetch Solana wallet balances and swap/transfer history via Helius Wallet API."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key = (config.get("api_key") or "").strip()
        self.wallet_addresses = self._parse_wallet_addresses(config)
        coingecko_key = (config.get("coingecko_api_key") or "").strip()
        self.coingecko = CoinGeckoClient(coingecko_key)
        self._mint_meta: Dict[str, Dict[str, Any]] = {}
        self._symbol_to_mint: Dict[str, str] = {}
        self._token_overrides: Dict[str, Dict[str, str]] = {
            str(k).upper(): v for k, v in (config.get("tokens") or {}).items()
        }
        for symbol, meta in self._token_overrides.items():
            mint = (meta or {}).get("mint")
            coin_id = (meta or {}).get("coingecko_id")
            if mint:
                self._symbol_to_mint[symbol] = mint
            if coin_id:
                self.coingecko.register_coin_id(symbol, coin_id)

    @staticmethod
    def _parse_wallet_addresses(config: Dict) -> List[str]:
        addresses: List[str] = []
        primary = (config.get("wallet_address") or "").strip()
        if primary:
            addresses.append(primary)
        for key in ("wallet_addresses", "addresses"):
            for entry in config.get(key) or []:
                if isinstance(entry, str):
                    value = entry.strip()
                elif isinstance(entry, dict):
                    value = str(entry.get("address", "")).strip()
                else:
                    value = ""
                if value:
                    addresses.append(value)
        return list(dict.fromkeys(addresses))

    def _headers(self) -> Dict[str, str]:
        return {"X-Api-Key": self.api_key}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        with httpx.Client(timeout=45.0) as client:
            response = client.get(
                f"{_BASE_URL}{path}",
                headers=self._headers(),
                params=params or {},
            )
            response.raise_for_status()
            return response.json()

    def _register_balance_row(self, row: Dict[str, Any]) -> None:
        mint = str(row.get("mint", "")).strip()
        if not mint:
            return
        symbol = str(row.get("symbol") or mint[:8]).upper().strip()
        self._mint_meta[mint] = {
            "symbol": symbol,
            "decimals": int(row.get("decimals") or 0),
            "price": row.get("pricePerToken"),
        }
        self._symbol_to_mint[symbol] = mint

    def _mint_for_symbol(self, symbol: str) -> Optional[str]:
        normalized = symbol.upper().strip()
        if not normalized:
            return None
        if normalized in self._symbol_to_mint:
            return self._symbol_to_mint[normalized]
        override = self._token_overrides.get(normalized) or {}
        return override.get("mint")

    def _symbol_for_mint(self, mint: str) -> str:
        meta = self._mint_meta.get(mint) or {}
        symbol = meta.get("symbol")
        if symbol:
            return str(symbol).upper()
        for sym, override in self._token_overrides.items():
            if override.get("mint") == mint:
                return sym
        if mint == _SOL_MINT:
            return "SOL"
        return mint[:8].upper()

    def _fetch_wallet_balances(self, wallet: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get(
                f"/v1/wallet/{wallet}/balances",
                {
                    "page": page,
                    "limit": _BALANCE_PAGE_LIMIT,
                    "showNative": True,
                    "showNfts": False,
                    "showZeroBalance": False,
                },
            )
            for row in payload.get("balances") or []:
                if isinstance(row, dict):
                    rows.append(row)
                    self._register_balance_row(row)
            pagination = payload.get("pagination") or {}
            if not pagination.get("hasMore"):
                break
            page += 1
        return rows

    async def fetch_balances(self) -> List[Dict]:
        """Aggregate SPL + SOL balances across configured wallet addresses."""
        if not self.api_key or not self.wallet_addresses:
            print("Helius connector missing api_key or wallet address.")
            return []

        totals: Dict[str, float] = {}
        try:
            for wallet in self.wallet_addresses:
                for row in self._fetch_wallet_balances(wallet):
                    quantity = float(row.get("balance") or 0)
                    if quantity <= 0:
                        continue
                    symbol = self._symbol_for_mint(str(row.get("mint", "")))
                    totals[symbol] = totals.get(symbol, 0.0) + quantity
        except Exception as exc:
            print(f"Error fetching Helius balances: {exc}")
            return []

        return [
            {"symbol": symbol, "quantity": quantity, "exchange": self.name}
            for symbol, quantity in sorted(totals.items())
            if quantity > 0
        ]

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Return USD prices using Helius balance pricing with CoinGecko fallback."""
        prices: Dict[str, float] = {}
        for symbol in symbols:
            normalized = symbol.upper().strip()
            mint = self._mint_for_symbol(normalized)
            spot: Optional[float] = None
            if mint:
                meta = self._mint_meta.get(mint) or {}
                raw_price = meta.get("price")
                try:
                    if raw_price is not None:
                        spot = float(raw_price)
                except (TypeError, ValueError):
                    spot = None
            if spot is None or spot <= 0:
                spot = self.coingecko.fetch_spot_usd(normalized)
            if spot and spot > 0:
                prices[normalized] = spot
        return prices

    def _fetch_history_page(
        self,
        wallet: str,
        *,
        before: Optional[str] = None,
        tx_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "limit": _HISTORY_PAGE_LIMIT,
            "tokenAccounts": "balanceChanged",
        }
        if before:
            params["before"] = before
        if tx_type:
            params["type"] = tx_type
        return self._get(f"/v1/wallet/{wallet}/history", params)

    def _iter_history(
        self,
        wallet: str,
        *,
        since_ms: Optional[int],
        paginate: bool,
    ):
        """Yield parsed history transactions newest-first, optionally walking pages."""
        before: Optional[str] = None
        while True:
            payload = self._fetch_history_page(wallet, before=before)
            rows = payload.get("data") or []
            if not rows:
                break

            reached_cutoff = False
            for tx in rows:
                ts = tx.get("timestamp")
                ts_ms = int(ts) * 1000 if ts is not None else None
                if since_ms is not None and ts_ms is not None and ts_ms < since_ms:
                    reached_cutoff = True
                    if not paginate:
                        return
                    continue
                yield tx

            pagination = payload.get("pagination") or {}
            if reached_cutoff and not paginate:
                return
            if not pagination.get("hasMore"):
                break
            before = pagination.get("nextCursor")
            if not before:
                break
            if reached_cutoff and paginate:
                return
            time.sleep(0.15)

    def _quote_usd_delta(self, changes: List[Dict[str, Any]]) -> float:
        """Estimate USD value exchanged in a transaction from quote-token movements."""
        usd_total = 0.0
        for change in changes:
            mint = str(change.get("mint", ""))
            try:
                amount = abs(float(change.get("amount") or 0))
            except (TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            if mint in (_USDC_MINT, _USDT_MINT):
                usd_total += amount
            elif mint == _SOL_MINT:
                sol_price = self.coingecko.fetch_spot_usd("SOL") or 0.0
                usd_total += amount * sol_price
        return usd_total

    def _normalize_history_order(
        self,
        tx: Dict[str, Any],
        *,
        target_mint: str,
        target_symbol: str,
    ) -> Optional[Dict[str, Any]]:
        if tx.get("error"):
            return None

        signature = str(tx.get("signature") or "").strip()
        if not signature:
            return None

        token_delta = 0.0
        for change in tx.get("balanceChanges") or []:
            if str(change.get("mint", "")) != target_mint:
                continue
            try:
                token_delta += float(change.get("amount") or 0)
            except (TypeError, ValueError):
                continue

        if token_delta == 0:
            return None

        order_type = "buy" if token_delta > 0 else "sell"
        quantity = abs(token_delta)
        usd_quote = self._quote_usd_delta(tx.get("balanceChanges") or [])
        price = usd_quote / quantity if usd_quote > 0 else 0.0
        if price <= 0:
            spot = self.coingecko.fetch_spot_usd(target_symbol)
            price = spot or 0.0

        ts = tx.get("timestamp")
        try:
            executed_at = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
                if ts is not None
                else datetime.utcnow()
            )
        except (TypeError, ValueError, OSError):
            executed_at = datetime.utcnow()

        return {
            "external_order_id": f"{signature}:{target_mint}",
            "symbol": target_symbol,
            "type": order_type,
            "quantity": quantity,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Map Helius wallet history balance changes to buy/sell order rows."""
        if not self.api_key or not self.wallet_addresses:
            return []

        symbol = market_pair.split("/")[0].upper().strip() if market_pair else ""
        target_mint = self._mint_for_symbol(symbol)
        if not target_mint:
            print(f"Helius: no mint mapping for symbol {symbol}.")
            return []

        if since_ms is None:
            since_ms = int(
                (datetime.now(tz=timezone.utc) - timedelta(days=_COLD_START_DAYS)).timestamp()
                * 1000
            )

        orders: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        for wallet in self.wallet_addresses:
            for tx in self._iter_history(wallet, since_ms=since_ms, paginate=paginate):
                row = self._normalize_history_order(
                    tx,
                    target_mint=target_mint,
                    target_symbol=symbol,
                )
                if not row:
                    continue
                ext_id = row["external_order_id"]
                if ext_id in seen_ids:
                    continue
                seen_ids.add(ext_id)
                orders.append(row)
                if len(orders) >= limit and not paginate:
                    break
            if len(orders) >= limit and not paginate:
                break

        orders.sort(key=lambda row: row["executed_at"])
        return orders

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        if not symbol:
            print("Helius fetch_orders requires a symbol.")
            return []
        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=90)).timestamp() * 1000
        )
        return self.fetch_orders_sync(symbol, since_ms, paginate=False)

    def fetch_price_history_sync(
        self,
        market_pair: str,
        since_ms: int,
        *,
        days: int,
    ) -> List[Dict[str, Any]]:
        """On-chain tokens use CoinGecko OHLC instead of CEX markets."""
        symbol = market_pair.split("/")[0].upper().strip() if market_pair else ""
        if not symbol:
            return []
        return self.coingecko.fetch_ohlc(symbol, days=days, since_ms=since_ms)

    def fetch_balance_at(
        self,
        wallet: str,
        mint: str,
        *,
        timestamp: datetime,
    ) -> Optional[float]:
        """Historical token balance at a point in time (Helius balance-at API)."""
        if not self.api_key:
            return None
        params = {
            "mint": mint,
            "time": int(timestamp.replace(tzinfo=timezone.utc).timestamp()),
        }
        try:
            payload = self._get(f"/v1/wallet/{wallet}/balance-at", params)
            return float(payload.get("balance") or 0)
        except Exception as exc:
            print(f"Helius balance-at failed for {wallet} {mint}: {exc}")
            return None

    async def test_connection(self) -> bool:
        if not self.api_key or not self.wallet_addresses:
            print("Helius connection test failed: missing api_key or wallet address.")
            return False
        try:
            self._fetch_wallet_balances(self.wallet_addresses[0])
            return True
        except Exception as exc:
            print(f"Helius connection test failed: {exc}")
            return False
