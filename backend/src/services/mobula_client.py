"""On-chain OHLCV from Mobula. Not a portfolio connector."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..utils.data_quality import ConnectorFetchError, positive_finite

_OHLCV_URL = "https://api.mobula.io/api/2/token/ohlcv-history"
# Mobula caps a single response at 2000 candles.
MAX_CANDLES_PER_REQUEST = 2000


def period_for_days(days: int) -> str:
    """Candle size for a lookback, matching centralized-exchange charts."""
    if days <= 1:
        return "1h"
    if days <= 7:
        return "4h"
    if days <= 30:
        return "12h"
    if days <= 90:
        return "1d"
    return "1w"


class MobulaClient:
    """Fetch USD token candles from Mobula's token OHLCV history endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        if api_key is None:
            from ..config.loader import get_section

            api_key = (get_section("mobula") or {}).get("api_key") or ""
        self.api_key = str(api_key).strip()
        self._transport = transport

    def fetch_ohlcv(
        self,
        address: str,
        chain_id: str,
        since_ms: int,
        *,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Return normalized candles from `since_ms` through now.

        `chain_id` is sent unchanged (positions.exchange is already `solana`
        or `ethereum`). Raises ConnectorFetchError when the key is missing or
        the HTTP call fails.
        """
        if not self.api_key:
            raise ConnectorFetchError("Mobula API key is not configured.")

        token_address = address.strip()
        chain = chain_id.strip()
        if not token_address or not chain:
            raise ConnectorFetchError(
                "Mobula OHLCV requires a token address and chain id."
            )

        period = period_for_days(days)
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        cursor = int(since_ms)
        points: List[Dict[str, Any]] = []
        seen_ts: set[int] = set()

        while cursor < now_ms:
            batch = self._get(
                {
                    "address": token_address,
                    "chainId": chain,
                    "period": period,
                    "from": cursor,
                    "to": now_ms,
                    "amount": MAX_CANDLES_PER_REQUEST,
                    "usd": "true",
                    "fill": "true",
                    "enableAssetHistory": "true",
                }
            )
            if not batch:
                break

            last_ts: Optional[int] = None
            for candle in batch:
                parsed = _normalize_candle(candle)
                if parsed is None:
                    continue
                ts_ms, point = parsed
                last_ts = ts_ms
                if ts_ms in seen_ts:
                    continue
                seen_ts.add(ts_ms)
                points.append(point)

            if last_ts is None or len(batch) < MAX_CANDLES_PER_REQUEST or last_ts >= now_ms:
                break
            next_cursor = last_ts + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor

        points.sort(key=lambda row: row["timestamp"])
        return points

    def _get(self, params: Dict[str, Any]) -> List[Any]:
        try:
            with httpx.Client(timeout=45.0, transport=self._transport) as client:
                response = client.get(
                    _OHLCV_URL,
                    params=params,
                    headers={"Authorization": self.api_key},
                )
        except httpx.HTTPError as exc:
            raise ConnectorFetchError(f"Mobula OHLCV request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:200].strip()
            raise ConnectorFetchError(
                f"Mobula OHLCV HTTP {response.status_code}: {detail}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorFetchError(
                "Mobula OHLCV response was not JSON."
            ) from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ConnectorFetchError(
                "Mobula OHLCV response did not include a data array."
            )
        return data


def _normalize_candle(candle: Any) -> Optional[tuple[int, Dict[str, Any]]]:
    if not isinstance(candle, dict):
        return None
    try:
        ts_ms = int(candle["t"])
        open_ = float(candle["o"])
        high = float(candle["h"])
        low = float(candle["l"])
        close = float(candle["c"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(positive_finite(value) for value in (open_, high, low, close)):
        return None
    point = {
        "timestamp": datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "price": close,
    }
    return ts_ms, point
