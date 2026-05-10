"""Coinbase exchange connector."""
import ccxt
from typing import Dict, List, Optional

from .base import BaseConnector


class CoinbaseConnector(BaseConnector):
    """Connector for Coinbase exchange."""

    def __init__(self, config: Dict):
        super().__init__(config)
        api_key = config.get("api_key", "")
        api_secret = config.get("api_secret", "")
        passphrase = config.get("passphrase", "")
        self.exchange = ccxt.coinbase(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": True,
            }
        )

    async def fetch_balances(self) -> List[Dict]:
        """Fetch balances from Coinbase."""
        try:
            balance = self.exchange.fetch_balance()
            balances = []
            for symbol, amount in balance["total"].items():
                if amount > 0 and symbol not in ["USD", "EUR"]:
                    balances.append(
                        {
                            "symbol": symbol,
                            "quantity": float(amount),
                            "exchange": "coinbase",
                        }
                    )
            return balances
        except Exception as e:
            print(f"Error fetching Coinbase balances: {e}")
            return []

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Fetch order history from Coinbase."""
        try:
            orders = []
            if symbol:
                pair = f"{symbol}/USD" if not "/" in symbol else symbol
                order_list = self.exchange.fetch_orders(pair)
            else:
                order_list = self.exchange.fetch_orders()

            for order in order_list:
                if order["status"] == "closed":
                    orders.append(
                        {
                            "symbol": order["symbol"].split("/")[0],
                            "type": "buy" if order["side"] == "buy" else "sell",
                            "quantity": float(order["filled"]),
                            "price": float(order["price"]),
                            "executed_at": order["datetime"],
                            "exchange": "coinbase",
                        }
                    )
            return orders
        except Exception as e:
            print(f"Error fetching Coinbase orders: {e}")
            return []

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current prices from Coinbase."""
        try:
            prices = {}
            for symbol in symbols:
                if "/" not in symbol:
                    pair = f"{symbol}/USD"
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
            print(f"Error fetching Coinbase prices: {e}")
            return {}

    async def test_connection(self) -> bool:
        """Test Coinbase connection."""
        try:
            self.exchange.load_markets()
            return True
        except Exception as e:
            print(f"Coinbase connection test failed: {e}")
            return False

