"""OKX exchange connector."""
import ccxt
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseConnector

# OKX order history is split between a 7-day endpoint and a 3-month archive.
_SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
# OKX caps closed-order page size at 100 (Binance allows up to 1000).
_OKX_ORDER_PAGE_LIMIT = 100


class OkxConnector(BaseConnector):
    """Connector for OKX exchange."""

    def __init__(self, config: Dict):
        super().__init__(config)
        api_key = config.get("api_key", "")
        api_secret = config.get("api_secret", "")
        passphrase = config.get("passphrase", "")
        self.exchange = ccxt.okx(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        if config.get("sandbox"):
            self.exchange.set_sandbox_mode(True)

    async def fetch_balances(self) -> List[Dict]:
        """Fetch balances from OKX trading account."""
        try:
            balance = self.exchange.fetch_balance()
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
            print(f"Error fetching OKX balances: {e}")
            return []

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
