"""Mobula wallet connector.

Balances and spot prices come from one portfolio call. The chain slug is
written to each row's `exchange` field — the connector name `mobula` is not.
Swap history is pulled separately, one page at a time, by the scheduler.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..services.mobula_client import (
    ACTIVITY_PAGE_SIZE,
    MobulaClient,
    chain_slug,
    extract_transactions,
    orders_from_transaction,
    portfolio_rows,
    transaction_time_ms,
)
from ..utils.data_quality import ConnectorFetchError, positive_finite
from .base import BaseConnector

_PLACEHOLDER_FRAGMENTS = ("your_", "_here", "changeme", "example", "placeholder")


def _missing_secret(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return any(fragment in text for fragment in _PLACEHOLDER_FRAGMENTS)


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    items: List[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text and text not in items and not _missing_secret(text):
            items.append(text)
    return items


def _chain_list(value: Any) -> List[str]:
    slugs: List[str] = []
    for item in _string_list(value):
        slug = chain_slug(item)
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


class MobulaConnector(BaseConnector):
    """Multichain wallet balances, swap detection, and contract OHLCV."""

    chain_scoped = True
    syncs_wallet_activity = True

    def __init__(self, config: Dict, client: Optional[MobulaClient] = None):
        super().__init__(config or {})
        self._api_key = str((config or {}).get("api_key") or "").strip()
        self._wallets = _string_list((config or {}).get("wallets"))
        self._chains = _chain_list((config or {}).get("blockchains"))
        self._client = client
        self._quotes: Dict[str, float] = {}

    def configured_chains(self) -> List[str]:
        return list(self._chains)

    def wallets(self) -> List[str]:
        return list(self._wallets)

    def _usable(self) -> bool:
        return not _missing_secret(self._api_key) and bool(self._wallets) and bool(self._chains)

    def _client_or_raise(self) -> MobulaClient:
        if not self._usable():
            raise ConnectorFetchError(
                "Mobula requires an API key, at least one wallet, and at least one blockchain."
            )
        if self._client is None:
            self._client = MobulaClient(self._api_key)
        return self._client

    async def fetch_balances(self) -> List[Dict]:
        client = self._client_or_raise()
        payload = client.portfolio(self._wallets, self._chains)
        rows = portfolio_rows(payload, self._chains)
        self._quotes = {}
        for row in rows:
            price = positive_finite(row.get("price"))
            if price is not None:
                self._quotes[row["symbol"]] = price
        return rows

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        return []

    def fetch_orders_sync(self, market_pair: str, since_ms: Optional[int], **kwargs) -> List[Dict]:
        """Per-symbol order sync is a no-op. Activity is fetched once per wallet."""
        return []

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Spot quotes captured by the portfolio call. No second HTTP request."""
        return {symbol: self._quotes[symbol] for symbol in symbols if symbol in self._quotes}

    async def test_connection(self) -> bool:
        """Local config check. Does not call Mobula."""
        return self._usable()

    def fetch_activity_page(
        self,
        wallet: str,
        *,
        from_ms: Optional[int] = None,
        to_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """One activity page and the swap orders parsed out of it."""
        client = self._client_or_raise()
        payload = client.activity(
            wallet,
            self._chains,
            from_ms=from_ms,
            to_ms=to_ms,
        )
        transactions = extract_transactions(payload)
        orders: List[Dict[str, Any]] = []
        times: List[int] = []
        allowed = set(self._chains)
        for tx in transactions:
            tx_ms = transaction_time_ms(tx)
            if tx_ms is not None:
                times.append(tx_ms)
            for row in orders_from_transaction(tx):
                if row["exchange"] in allowed:
                    orders.append(row)
        return {
            "orders": orders,
            "count": len(transactions),
            "page_size": ACTIVITY_PAGE_SIZE,
            "oldest_tx_ms": min(times) if times else None,
            "newest_tx_ms": max(times) if times else None,
        }
