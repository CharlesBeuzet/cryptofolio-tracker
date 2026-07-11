"""CoinGecko API client for on-chain token price history."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

_BASE_URL = "https://api.coingecko.com/api/v3"
_SOL_ID = "solana"
_STABLECOIN_IDS = {"tether": "USDT", "usd-coin": "USDC"}


def _ohlc_days_param(days: int) -> str:
    """Map requested chart range to CoinGecko OHLC days enum."""
    if days <= 1:
        return "1"
    if days <= 7:
        return "7"
    if days <= 14:
        return "14"
    if days <= 30:
        return "30"
    if days <= 90:
        return "90"
    if days <= 180:
        return "180"
    return "365"


class CoinGeckoClient:
    """Resolve symbols to CoinGecko IDs and fetch OHLC / spot prices."""

    def __init__(self, api_key: str = ""):
        self.api_key = (api_key or "").strip()
        self._coin_id_cache: Dict[str, str] = {}
        self._spot_cache: Dict[str, tuple[float, float]] = {}

    def _headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"x-cg-pro-api-key": self.api_key}
        return {}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{_BASE_URL}{path}",
                params=params or {},
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def register_coin_id(self, symbol: str, coin_id: str) -> None:
        """Pin a symbol to a specific CoinGecko coin ID (config overrides)."""
        self._coin_id_cache[symbol.upper().strip()] = coin_id.strip()

    def resolve_coin_id(self, symbol: str) -> Optional[str]:
        """Resolve a ticker symbol to a CoinGecko coin ID."""
        normalized = symbol.upper().strip()
        if not normalized:
            return None
        if normalized == "SOL":
            return _SOL_ID
        if normalized in ("USDT", "USDC"):
            return "tether" if normalized == "USDT" else "usd-coin"

        cached = self._coin_id_cache.get(normalized)
        if cached:
            return cached

        try:
            payload = self._get("/search", {"query": normalized})
        except Exception as exc:
            print(f"CoinGecko search failed for {normalized}: {exc}")
            return None

        coins = payload.get("coins") or []
        for coin in coins:
            if str(coin.get("symbol", "")).upper() == normalized:
                coin_id = str(coin.get("id", "")).strip()
                if coin_id:
                    self._coin_id_cache[normalized] = coin_id
                    return coin_id

        if coins:
            coin_id = str(coins[0].get("id", "")).strip()
            if coin_id:
                self._coin_id_cache[normalized] = coin_id
                return coin_id
        return None

    def fetch_spot_usd(self, symbol: str) -> Optional[float]:
        """Return the current USD spot price for a symbol."""
        coin_id = self.resolve_coin_id(symbol)
        if not coin_id:
            return None

        now = time.monotonic()
        cached = self._spot_cache.get(coin_id)
        if cached and now - cached[0] < 120:
            return cached[1]

        try:
            payload = self._get(
                "/simple/price",
                {"ids": coin_id, "vs_currencies": "usd"},
            )
            price = float(payload.get(coin_id, {}).get("usd", 0))
        except Exception as exc:
            print(f"CoinGecko spot price failed for {symbol}: {exc}")
            return None

        if price > 0:
            self._spot_cache[coin_id] = (now, price)
            return price
        return None

    def fetch_ohlc(
        self,
        symbol: str,
        *,
        days: int,
        since_ms: int,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLC candles for a symbol, filtered to the requested window."""
        coin_id = self.resolve_coin_id(symbol)
        if not coin_id:
            return []

        try:
            raw = self._get(
                f"/coins/{coin_id}/ohlc",
                {"vs_currency": "usd", "days": _ohlc_days_param(days)},
            )
        except Exception as exc:
            print(f"CoinGecko OHLC failed for {symbol}: {exc}")
            return []

        points: List[Dict[str, Any]] = []
        seen_ts: set[int] = set()
        for candle in raw or []:
            if not isinstance(candle, list) or len(candle) < 5:
                continue
            ts_ms = int(candle[0])
            if ts_ms < since_ms or ts_ms in seen_ts:
                continue
            seen_ts.add(ts_ms)
            try:
                open_ = float(candle[1])
                high = float(candle[2])
                low = float(candle[3])
                close = float(candle[4])
            except (TypeError, ValueError):
                continue
            points.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        ts_ms / 1000.0, tz=timezone.utc
                    ),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "price": close,
                }
            )
        points.sort(key=lambda row: row["timestamp"])
        return points
