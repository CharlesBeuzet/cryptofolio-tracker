"""Binance exchange connector."""
import ccxt
from typing import Dict, List, Optional

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
                if amount > 0 and symbol not in ["USDT", "USDC", "BUSD", "EUR"]:
                    # Convert to USDT pair for price lookup
                    if symbol == "BTC":
                        pair = "BTC/USDT"
                    elif symbol == "ETH":
                        pair = "ETH/USDT"
                    else:
                        pair = f"{symbol}/USDT"
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

