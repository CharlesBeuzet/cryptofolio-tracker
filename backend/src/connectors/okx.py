"""OKX exchange connector."""
import ccxt
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from ..utils.data_quality import ConnectorFetchError, positive_finite
from .base import BaseConnector

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
        except Exception as e:
            print(f"Error fetching OKX {account_type} balances: {e}")
            raise ConnectorFetchError(
                f"okx {account_type} balances: {e}"
            ) from e
        totals = balance.get("total") if isinstance(balance, dict) else None
        if not isinstance(totals, dict):
            raise ConnectorFetchError(
                f"okx {account_type} balances: missing total map"
            )
        balances = []
        for symbol, amount in totals.items():
            try:
                qty = float(amount)
            except (TypeError, ValueError):
                continue
            if qty > 0:
                balances.append(
                    {
                        "symbol": symbol,
                        "quantity": qty,
                        "exchange": self.name,
                    }
                )
        return balances

    async def fetch_balances(self) -> List[Dict]:
        """Fetch balances from OKX trading and funding accounts (aggregated per symbol).

        Any wallet-type failure aborts the whole fetch so callers do not persist
        a partial book that would close missing positions.
        """
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
        """Pair-level fetch. Do not pass since: OKX filters it on cTime, not fill time."""
        params: Dict[str, Any] = {}
        if paginate:
            params["paginate"] = True
        kwargs: Dict[str, Any] = {
            "limit": min(max(limit, 1), _OKX_ORDER_PAGE_LIMIT),
            "params": params,
        }
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
            raise ConnectorFetchError(
                f"okx orders for {market_pair}: {e}"
            ) from e

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Fetch archived order history from OKX, optionally filtered to one base/pair."""
        symbols = []
        if symbol:
            symbols = [symbol.split("/")[0] if "/" in symbol else symbol]
        orders = self.fetch_archived_orders_sync(symbols)
        if not symbols:
            return orders
        wanted = {s.upper() for s in symbols}
        return [row for row in orders if str(row.get("symbol", "")).upper() in wanted]

    def _normalize_raw_okx_order(
        self, raw_order: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Normalize a raw OKX order response row (without market_pair context).

        OKX raw fields: ordId, instId (e.g. PUMP-USDC), state, side, fillSz, avgPx,
        uTime (fill time ms).
        """
        state = raw_order.get("state")
        if state != "filled":
            return None
        order_id = raw_order.get("ordId")
        if order_id is None:
            return None
        inst_id = raw_order.get("instId") or ""
        base = inst_id.split("-")[0] if "-" in inst_id else inst_id
        if not base:
            return None
        ts_ms = raw_order.get("uTime") or raw_order.get("cTime")
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
            quantity = float(raw_order.get("fillSz") or raw_order.get("sz") or 0)
            price = float(raw_order.get("avgPx") or raw_order.get("px") or 0)
        except (TypeError, ValueError):
            return None
        if quantity <= 0:
            return None
        if positive_finite(price) is None:
            return None
        return {
            "external_order_id": str(order_id),
            "symbol": base,
            "type": "buy" if raw_order.get("side") == "buy" else "sell",
            "quantity": quantity,
            "price": price,
            "executed_at": executed_at,
            "exchange": self.name,
        }

    def _fetch_spot_order_history(self, path: str) -> List[Dict[str, Any]]:
        """Account-wide executed spot orders (no instId, no begin).

        path is trade/orders-history (completed in 7 days) or
        trade/orders-history-archive (last ~3 months). Paginates with after=ordId.
        """
        all_orders: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        after_cursor: Optional[str] = None

        while True:
            params: Dict[str, Any] = {
                "instType": "SPOT",
                "limit": str(_OKX_ORDER_PAGE_LIMIT),
            }
            if after_cursor:
                params["after"] = after_cursor

            try:
                resp = self.exchange.request(path, "private", "GET", params)
            except Exception as e:
                print(f"Error fetching OKX {path}: {e}")
                raise ConnectorFetchError(f"okx {path}: {e}") from e

            rows = self._okx_response_rows(resp, path)
            if not rows:
                break

            for raw_order in rows:
                if not isinstance(raw_order, dict):
                    continue
                order_id = raw_order.get("ordId")
                if not order_id or order_id in seen_ids:
                    continue
                seen_ids.add(str(order_id))
                normalized = self._normalize_raw_okx_order(raw_order)
                if normalized:
                    all_orders.append(normalized)
                after_cursor = str(order_id)

            if len(rows) < _OKX_ORDER_PAGE_LIMIT:
                break

        return all_orders

    def fetch_recent_orders_sync(
        self, symbols: Sequence[str]
    ) -> List[Dict[str, Any]]:
        """Executed spot orders completed in the last 7 days (account-wide).

        Ignores `symbols`: OKX /trade/orders-history with instType=SPOT, no instId,
        no begin. That includes orders placed earlier and filled in the window.
        """
        del symbols
        return self._fetch_spot_order_history("trade/orders-history")

    def fetch_archived_orders_sync(
        self, symbols: Sequence[str]
    ) -> List[Dict[str, Any]]:
        """OKX 3-month archive, account-wide, no begin (cold start / catch-up)."""
        del symbols
        return self._fetch_spot_order_history("trade/orders-history-archive")

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices from OKX.

        Per-symbol ticker failures are skipped. A transport-level failure
        raises ConnectorFetchError instead of returning {}.
        """
        try:
            prices = {}
            for symbol in symbols:
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
                        print(f"Ignoring invalid OKX price for {pair}: {last}")
                except Exception as e:
                    print(f"Error fetching price for {pair}: {e}")
                    continue
            return prices
        except ConnectorFetchError:
            raise
        except Exception as e:
            print(f"Error fetching OKX prices: {e}")
            raise ConnectorFetchError(f"okx prices: {e}") from e

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
            raise ConnectorFetchError(f"okx fiat deposits: {e}") from e

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
