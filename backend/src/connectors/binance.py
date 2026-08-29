"""Binance exchange connector."""
import ccxt
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..utils.data_quality import ConnectorFetchError, positive_finite
from .base import BaseConnector


class BinanceConnector(BaseConnector):
    """Connector for Binance exchange."""

    def __init__(self, config: Dict):
        super().__init__(config)
        api_key = config.get("api_key", "")
        api_secret = config.get("api_secret", "")
        self.exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},  # Use spot trading
            }
        )

    async def fetch_balances(self) -> List[Dict]:
        """Fetch balances from Binance.

        Raises ConnectorFetchError on request failure so callers do not treat
        an empty list as "the account has no holdings".
        """
        try:
            balance = self.exchange.fetch_balance()
        except Exception as e:
            print(f"Error fetching Binance balances: {e}")
            raise ConnectorFetchError(f"binance balances: {e}") from e
        totals = balance.get("total") if isinstance(balance, dict) else None
        if not isinstance(totals, dict):
            raise ConnectorFetchError("binance balances: missing total map")
        balances = []
        for symbol, amount in totals.items():
            # Skip fiat buckets and deprecated BUSD listing noise but track everything else
            try:
                qty = float(amount)
            except (TypeError, ValueError):
                continue
            if qty > 0 and symbol not in ["BUSD", "EUR"]:
                balances.append(
                    {
                        "symbol": symbol,
                        "quantity": qty,
                        "exchange": "binance",
                    }
                )
        return balances

    def _normalize_executed_order(
        self, order: Dict[str, Any], market_pair: str
    ) -> Optional[Dict[str, Any]]:
        if order.get("status") != "closed":
            return None
        order_id = order.get("id")
        if order_id is None:
            return None
        ts_ms = order.get("lastTradeTimestamp") or order.get("timestamp")
        try:
            if ts_ms is not None:
                executed_at = datetime.fromtimestamp(
                    int(ts_ms) / 1000.0, tz=timezone.utc
                ).replace(tzinfo=None)
            else:
                executed_at = datetime.utcnow()
        except (TypeError, ValueError, OSError):
            executed_at = datetime.utcnow()
        try:
            quantity = float(order.get("filled") or 0)
            price = float(order.get("average") or order.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if quantity <= 0:
            return None
        if positive_finite(price) is None:
            return None
        base = market_pair.split("/")[0] if "/" in market_pair else market_pair
        return {
            "external_order_id": str(order_id),
            "symbol": base,
            "type": "buy" if order.get("side") == "buy" else "sell",
            "quantity": quantity,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def _fetch_executed_orders(
        self,
        market_pair: str,
        since_ms: Optional[int],
        limit: int,
        paginate: bool,
    ) -> List[Dict[str, Any]]:
        """ccxt names this fetch_closed_orders; we treat fully filled orders as executed."""
        params: Dict[str, Any] = {}
        if paginate:
            params["paginate"] = True
        kwargs: Dict[str, Any] = {"limit": limit, "params": params}
        if since_ms is not None:
            kwargs["since"] = since_ms
        return self.exchange.fetch_closed_orders(market_pair, **kwargs)

    def fetch_orders_sync(
        self,
        market_pair: str,
        since_ms: Optional[int],
        *,
        limit: int = 500,
        paginate: bool = False,
    ) -> List[Dict[str, Any]]:
        """Fetch executed spot orders for one pair (sync, for scheduler)."""
        try:
            executed_orders = self._fetch_executed_orders(
                market_pair,
                since_ms,
                limit=min(max(limit, 1), 1000),
                paginate=paginate,
            )
            out: List[Dict[str, Any]] = []
            for order in executed_orders:
                row = self._normalize_executed_order(order, market_pair)
                if row:
                    out.append(row)
            return out
        except Exception as e:
            print(f"Error fetching Binance orders for {market_pair}: {e}")
            raise ConnectorFetchError(
                f"binance orders for {market_pair}: {e}"
            ) from e

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Fetch order history from Binance for one base symbol or market pair."""
        if not symbol:
            print("Binance fetch_orders requires a symbol or market pair.")
            return []
        if "/" in symbol:
            pairs = [symbol]
        else:
            pairs = [
                f"{symbol}/{quote}"
                for quote in ("USDT", "USDC")
                if symbol != quote
            ]
        since_ms = int(
            (datetime.now(tz=timezone.utc) - timedelta(days=90)).timestamp() * 1000
        )
        orders: List[Dict] = []
        seen_ids: set[str] = set()
        for market_pair in pairs:
            for row in self.fetch_orders_sync(
                market_pair, since_ms=since_ms, limit=500, paginate=False
            ):
                ext_id = row.get("external_order_id")
                if ext_id and ext_id in seen_ids:
                    continue
                if ext_id:
                    seen_ids.add(ext_id)
                orders.append(row)
        return orders


    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices from Binance.

        Per-symbol ticker failures are skipped. A transport-level failure
        raises ConnectorFetchError instead of returning {}.
        """
        try:
            prices = {}
            for symbol in symbols:
                # Ensure symbol is in correct format
                if "/" not in symbol:
                    pair = f"{symbol}/USDT"
                else:
                    pair = symbol
                try:
                    ticker = self.exchange.fetch_ticker(pair)
                    last = ticker.get("last") if isinstance(ticker, dict) else None
                    parsed_last = positive_finite(last)
                    if parsed_last is not None:
                        prices[symbol] = parsed_last
                    else:
                        print(f"Ignoring invalid Binance price for {pair}: {last}")
                except Exception as e:
                    print(f"Error fetching price for {pair}: {e}")
                    continue
            return prices
        except ConnectorFetchError:
            raise
        except Exception as e:
            print(f"Error fetching Binance prices: {e}")
            raise ConnectorFetchError(f"binance prices: {e}") from e

    async def test_connection(self) -> bool:
        """Test Binance connection."""
        try:
            self.exchange.load_markets()
            return True
        except Exception as e:
            print(f"Binance connection test failed: {e}")
            return False

    def fetch_fiat_deposit_orders_sync(self, rows: int = 100) -> List[Dict[str, Any]]:
        """
        Binance SAPI fiat deposits (transactionType=0) from both fiat/orders and fiat/payments.
        Both endpoints are queried each sync (same parameters); rows are normalized and deduped
        by orderNo (fiat/orders wins over fiat/payments when both list the same order).
        Implements BaseConnector.fetch_fiat_deposit_orders_sync.
        Set at parameter to the past one year.
        """
        n = min(max(rows, 1), 500)
        params = {
            "transactionType": 0,
            "rows": n,
        }

        def _data_rows(resp: Any, label: str) -> List[Dict[str, Any]]:
            if resp is None:
                return []
            code = resp.get("code")
            if code not in (None, "000000", 0, "0"):
                print(f"Binance {label} returned code={code} message={resp.get('message')}")
                return []
            raw = resp.get("data") or []
            return raw if isinstance(raw, list) else []

        def _normalize_row(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            order_no = item.get("orderNo")
            if not order_no:
                return None
            try:
                amt = float(
                    item.get("amount")
                    or item.get("indicatedAmount")
                    or item.get("sourceAmount")
                    or 0
                )
            except (TypeError, ValueError):
                amt = 0.0
            fee_raw = item.get("totalFee") or item.get("fee")
            try:
                fee = float(fee_raw) if fee_raw is not None else None
            except (TypeError, ValueError):
                fee = None
            ts_ms = item.get("createTime") or item.get("updateTime")
            try:
                ts_ms = int(ts_ms)
                deposited_at = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).replace(
                    tzinfo=None
                )
            except (TypeError, ValueError, OSError):
                deposited_at = datetime.utcnow()
            return {
                "external_order_id": str(order_no),
                "currency": str(item.get("fiatCurrency") or "").upper() or "UNKNOWN",
                "amount": amt,
                "fee": fee,
                "status": item.get("status"),
                "method": item.get("paymentMethod") or item.get("method"),
                "deposited_at": deposited_at,
            }

        def _get_orders():
            try:
                return self.exchange.sapi_get_fiat_orders(params)
            except Exception as e:
                print(f"Error fetching Binance sapi_get_fiat_orders: {e}")
                return None

        def _get_payments():
            try:
                return self.exchange.sapi_get_fiat_payments(params)
            except Exception as e:
                print(f"Error fetching Binance sapi_get_fiat_payments: {e}")
                return None

        # Sequential calls: shared ccxt exchange instance is not guaranteed thread-safe.
        resp_orders = _get_orders()
        resp_payments = _get_payments()
        if resp_orders is None and resp_payments is None:
            raise ConnectorFetchError("binance fiat deposits: both endpoints failed")

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for label, resp in (
            ("fiat/orders", resp_orders),
            ("fiat/payments", resp_payments),
        ):
            for item in _data_rows(resp, label):
                if not isinstance(item, dict):
                    continue
                row = _normalize_row(item)
                if not row:
                    continue
                oid = row["external_order_id"]
                if oid in seen:
                    continue
                seen.add(oid)
                out.append(row)
        return out

