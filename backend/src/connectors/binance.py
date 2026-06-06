"""Binance exchange connector."""
import ccxt
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        """Fetch balances from Binance."""
        try:
            balance = self.exchange.fetch_balance()
            balances = []
            for symbol, amount in balance["total"].items():
                # Skip fiat buckets and deprecated BUSD listing noise but track everything else
                if amount > 0 and symbol not in ["BUSD", "EUR"]:
                    balances.append(
                        {
                            "symbol": symbol,
                            "quantity": float(amount),
                            "exchange": "binance",
                        }
                    )
            return balances
        except Exception as e:
            print(f"Error fetching Binance balances: {e}")
            return []

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Fetch order history from Binance."""
        try:
            orders = []
            if symbol:
                # Fetch orders for specific symbol
                pair = f"{symbol}/USDT" if not "/" in symbol else symbol
                order_list = self.exchange.fetch_orders(pair)
            else:
                # Fetch all orders (this might be limited by exchange)
                order_list = self.exchange.fetch_orders()

            for order in order_list:
                if order["status"] == "closed":  # Only completed orders
                    orders.append(
                        {
                            "symbol": order["symbol"].split("/")[0],
                            "type": "buy" if order["side"] == "buy" else "sell",
                            "quantity": float(order["filled"]),
                            "price": float(order["price"]),
                            "executed_at": order["datetime"],
                            "exchange": "binance",
                        }
                    )
            return orders
        except Exception as e:
            print(f"Error fetching Binance orders: {e}")
            return []

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices from Binance."""
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
                    prices[symbol] = float(ticker["last"])
                except Exception as e:
                    print(f"Error fetching price for {pair}: {e}")
                    continue
            return prices
        except Exception as e:
            print(f"Error fetching Binance prices: {e}")
            return {}

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

