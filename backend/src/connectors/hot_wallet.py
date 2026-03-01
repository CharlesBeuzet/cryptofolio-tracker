"""Hot wallet connector for blockchain addresses."""
from typing import Dict, List, Optional
from web3 import Web3
from datetime import datetime

from .base import BaseConnector


class HotWalletConnector(BaseConnector):
    """Connector for hot wallets (Ethereum and EVM-compatible chains)."""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.addresses = config.get("addresses", [])
        self.rpc_urls = config.get("rpc_urls", {})
        # Default to Ethereum mainnet if not specified
        self.default_rpc = config.get("default_rpc", "https://eth.llamarpc.com")
        self.w3 = Web3(Web3.HTTPProvider(self.default_rpc))

    async def fetch_balances(self) -> List[Dict]:
        """Fetch token balances from wallet addresses."""
        balances = []
        try:
            for address_config in self.addresses:
                address = address_config.get("address", "")
                chain = address_config.get("chain", "ethereum")
                rpc_url = self.rpc_urls.get(chain, self.default_rpc)

                if chain != "ethereum":
                    # For other chains, create a new Web3 instance
                    w3 = Web3(Web3.HTTPProvider(rpc_url))
                else:
                    w3 = self.w3

                if not w3.is_address(address):
                    continue

                # Fetch native token balance (ETH, BNB, etc.)
                native_balance = w3.eth.get_balance(address)
                native_symbol = "ETH" if chain == "ethereum" else chain.upper()
                if native_balance > 0:
                    balances.append(
                        {
                            "symbol": native_symbol,
                            "quantity": float(w3.from_wei(native_balance, "ether")),
                            "exchange": f"wallet_{chain}",
                        }
                    )

                # Fetch ERC-20 token balances if specified
                tokens = address_config.get("tokens", [])
                for token_config in tokens:
                    token_address = token_config.get("address", "")
                    token_symbol = token_config.get("symbol", "")
                    token_decimals = token_config.get("decimals", 18)

                    if not w3.is_address(token_address):
                        continue

                    # ERC-20 balanceOf ABI
                    abi = [
                        {
                            "constant": True,
                            "inputs": [{"name": "_owner", "type": "address"}],
                            "name": "balanceOf",
                            "outputs": [{"name": "balance", "type": "uint256"}],
                            "type": "function",
                        }
                    ]

                    try:
                        contract = w3.eth.contract(
                            address=Web3.to_checksum_address(token_address), abi=abi
                        )
                        balance = contract.functions.balanceOf(
                            Web3.to_checksum_address(address)
                        ).call()
                        if balance > 0:
                            token_balance = balance / (10 ** token_decimals)
                            balances.append(
                                {
                                    "symbol": token_symbol,
                                    "quantity": float(token_balance),
                                    "exchange": f"wallet_{chain}",
                                }
                            )
                    except Exception as e:
                        print(f"Error fetching token {token_symbol} balance: {e}")
                        continue

        except Exception as e:
            print(f"Error fetching wallet balances: {e}")
        return balances

    async def fetch_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Fetch order history from wallets.
        Note: Wallets don't have order history in the traditional sense.
        This would require blockchain transaction analysis which is complex.
        For V0, we return empty list. This can be enhanced in v2.
        """
        # Wallet transactions are not "orders" in the exchange sense
        # This would require parsing blockchain transactions
        return []

    async def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch current prices for wallet tokens.
        Note: This connector doesn't fetch prices directly.
        Prices should be fetched from an exchange connector or price API.
        """
        # For V0, we don't fetch prices here
        # Prices should be fetched from exchange connectors
        return {}

    async def test_connection(self) -> bool:
        """Test wallet connection by checking RPC connectivity."""
        try:
            return self.w3.is_connected()
        except Exception as e:
            print(f"Wallet connection test failed: {e}")
            return False

