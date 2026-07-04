"""OKX exchange connector."""
import ccxt
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseConnector

# OKX order history is split between a 7-day endpoint and a 3-month archive.
_SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
# OKX caps closed-order page size at 100 (Binance allows up to 1000).
_OKX_ORDER_PAGE_LIMIT = 100
# OKX fiat deposit history page size cap.
_OKX_FIAT_DEPOSIT_PAGE_LIMIT = 100
# OKX wallet types for balance fetch (ccxt params.type).
_OKX_BALANCE_ACCOUNT_TYPES = ("trading", "funding")


class OkxConnector(BaseConnector):
    """Connector for OKX exchange."""

    def __init__(self, config: Dict):
        super().__init__(config)
        api_key = config.get("api_key", "")
        api_secret = config.get("api_secret", "")
        passphrase = config.get("passphrase", "")
        exchange_config: Dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        hostname = config.get("hostname")
        if hostname:
            exchange_config["hostname"] = hostname
        self.exchange = ccxt.okx(exchange_config)
        if config.get("sandbox"):
            self.exchange.set_sandbox_mode(True)

    def _fetch_account_balances(self, account_type: str) -> List[Dict]:
        """Fetch non-zero balances from one OKX wallet (trading or funding)."""
        try:
            balance = self.exchange.fetch_balance({"type": account_type})
            balances = []
            for symbol, amount in balance["total"].items():
                if amount > 0:
                    balances.append(
                        {
                            "symbol": symbol,
                            "quantity": float(amount),
                            "exchange": self.name,
                        }
                    )
            return balances
        except Exception as e:
            print(f"Error fetching OKX {account_type} balances: {e}")
            return []

    async def fetch_balances(self) -> List[Dict]:
        """Fetch balances from OKX trading and funding accounts (aggregated per symbol)."""
        totals: Dict[str, float] = defaultdict(float)
        for account_type in _OKX_BALANCE_ACCOUNT_TYPES:
            for row in self._fetch_account_balances(account_type):
                totals[row["symbol"]] += row["quantity"]
        return [
            {"symbol": sym, "quantity": qty, "exchange": self.name}
            for sym, qty in sorted(totals.items())
            if qty > 0
        ]

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

    def _history_method_for_since(self, since_ms: Optional[int]) -> Optional[str]:
        if since_ms is None:
            return None
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        if now_ms - since_ms > _SEVEN_DAYS_MS:
            return "privateGetTradeOrdersHistoryArchive"
        return None

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
        archive_method = self._history_method_for_since(since_ms)
        if archive_method is not None:
            params["method"] = archive_method
        kwargs: Dict[str, Any] = {
            "limit": min(max(limit, 1), _OKX_ORDER_PAGE_LIMIT),
            "params": params,
        }
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
                limit=limit,
                paginate=paginate,
            )
            out: List[Dict[str, Any]] = []
            for order in executed_orders:
                row = self._normalize_executed_order(order, market_pair)
                if row:
                    out.append(row)
            return out
        except Exception as e:
            print(f"Error fetching OKX orders for {market_pair}: {e}")
            return []

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Fetch order history from OKX for one base symbol or market pair."""
        if not symbol:
            print("OKX fetch_orders requires a symbol or market pair.")
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
                market_pair, since_ms=since_ms, limit=_OKX_ORDER_PAGE_LIMIT, paginate=True
            ):
                ext_id = row.get("external_order_id")
                if ext_id and ext_id in seen_ids:
                    continue
                if ext_id:
                    seen_ids.add(ext_id)
                orders.append(row)
        return orders

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices from OKX."""
        try:
            prices = {}
            for symbol in symbols:
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
            print(f"Error fetching OKX prices: {e}")
            return {}

    async def test_connection(self) -> bool:
        """Test OKX connection."""
        try:
            self.exchange.load_markets()
            return True
        except Exception as e:
            print(f"OKX connection test failed: {e}")
            return False

    def _private_get_fiat_deposit_order_history(
        self, params: Dict[str, Any]
    ) -> Any:
        """
        GET /api/v5/fiat/deposit-order-history via ccxt signing (not in ccxt.okx yet).
        """
        return self.exchange.request(
            "fiat/deposit-order-history",
            "private",
            "GET",
            params,
        )

    def _okx_response_rows(self, resp: Any, label: str) -> List[Dict[str, Any]]:
        if resp is None:
            return []
        code = resp.get("code")
        if code not in (None, "0", 0):
            print(
                f"OKX {label} returned code={code} message={resp.get('msg')}"
            )
            return []
        raw = resp.get("data") or []
        return raw if isinstance(raw, list) else []

    def _normalize_fiat_deposit_row(
        self, item: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        order_id = item.get("ordId")
        if not order_id:
            return None
        try:
            amount = float(item.get("amt") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        fee_raw = item.get("fee")
        try:
            fee = float(fee_raw) if fee_raw is not None else None
        except (TypeError, ValueError):
            fee = None
        ts_ms = item.get("cTime") or item.get("uTime")
        try:
            ts_ms = int(ts_ms)
            deposited_at = datetime.fromtimestamp(
                ts_ms / 1000.0, tz=timezone.utc
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            deposited_at = datetime.utcnow()
        return {
            "external_order_id": str(order_id),
            "currency": str(item.get("ccy") or "").upper() or "UNKNOWN",
            "amount": amount,
            "fee": fee,
            "status": item.get("state"),
            "method": item.get("paymentMethod"),
            "deposited_at": deposited_at,
        }

    def fetch_fiat_deposit_orders_sync(self, rows: int = 100) -> List[Dict[str, Any]]:
        """
        OKX fiat deposit order history (GET /api/v5/fiat/deposit-order-history).
        Implements BaseConnector.fetch_fiat_deposit_orders_sync.
        """
        n = min(max(rows, 1), _OKX_FIAT_DEPOSIT_PAGE_LIMIT)
        params = {"limit": str(n)}

        try:
            resp = self._private_get_fiat_deposit_order_history(params)
        except Exception as e:
            print(f"Error fetching OKX fiat/deposit-order-history: {e}")
            return []

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in self._okx_response_rows(resp, "fiat/deposit-order-history"):
            if not isinstance(item, dict):
                continue
            row = self._normalize_fiat_deposit_row(item)
            if not row:
                continue
            oid = row["external_order_id"]
            if oid in seen:
                continue
            seen.add(oid)
            out.append(row)
        return out
