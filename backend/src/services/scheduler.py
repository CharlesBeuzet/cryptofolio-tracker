"""Scheduler service for periodic data updates."""
import asyncio
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from ..models.database import SessionLocal, PortfolioSnapshot, Asset
from ..connectors.base import BaseConnector
from ..connectors.binance import BinanceConnector
from ..connectors.coinbase import CoinbaseConnector
from ..connectors.hot_wallet import HotWalletConnector
from .portfolio import PortfolioService


class DataUpdateScheduler:
    """Scheduler for updating portfolio data from all connectors."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            # Get project root directory
            BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            config_path = str(BASE_DIR / "settings" / "config.yaml")
        self.config_path = config_path
        self.scheduler = AsyncIOScheduler()
        self.connectors: List[BaseConnector] = []
        self._load_connectors()

    def _load_connectors(self):
        """Load connectors from configuration."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            print(f"Warning: Config file {self.config_path} not found. Skipping connector setup.")
            return

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        # Initialize Binance connector
        if config.get("binance"):
            try:
                self.connectors.append(BinanceConnector(config["binance"]))
                print("Binance connector initialized")
            except Exception as e:
                print(f"Failed to initialize Binance connector: {e}")

        # Initialize Coinbase connector
        if config.get("coinbase"):
            try:
                self.connectors.append(CoinbaseConnector(config["coinbase"]))
                print("Coinbase connector initialized")
            except Exception as e:
                print(f"Failed to initialize Coinbase connector: {e}")

        # Initialize Hot Wallet connector
        if config.get("hot_wallets"):
            try:
                self.connectors.append(HotWalletConnector(config["hot_wallets"]))
                print("Hot Wallet connector initialized")
            except Exception as e:
                print(f"Failed to initialize Hot Wallet connector: {e}")

    async def update_portfolio_data(self):
        """Update portfolio data from all connectors."""
        print("Starting portfolio data update...")
        db = SessionLocal()
        try:
            # Collect all balances from all connectors
            all_balances = []
            all_symbols = set()

            for connector in self.connectors:
                try:
                    balances = await connector.fetch_balances()
                    all_balances.extend(balances)
                    all_symbols.update([b["symbol"] for b in balances])
                except Exception as e:
                    print(f"Error fetching balances from {connector.name}: {e}")

            # Fetch prices for all symbols
            # Use first available connector that supports price fetching
            prices = {}
            for connector in self.connectors:
                if hasattr(connector, "fetch_prices") and connector.name in ["binance", "coinbase"]:
                    try:
                        prices = await connector.fetch_prices(list(all_symbols))
                        break
                    except Exception as e:
                        print(f"Error fetching prices from {connector.name}: {e}")

            # Update positions
            portfolio_service = PortfolioService(db)
            for balance in all_balances:
                symbol = balance["symbol"]
                quantity = balance["quantity"]
                exchange = balance["exchange"]
                price = prices.get(symbol)

                # Update or create asset
                asset = db.query(Asset).filter(Asset.symbol == symbol).first()
                if not asset:
                    asset = Asset(symbol=symbol, name=symbol)
                    db.add(asset)
                    db.flush()

                if price:
                    asset.current_price = price
                    asset.last_updated = datetime.utcnow()

                # Update position
                portfolio_service.update_position_from_balance(
                    symbol, quantity, exchange, price
                )

            # Create portfolio snapshot
            total_value = portfolio_service.get_portfolio_value()
            snapshot = PortfolioSnapshot(total_value=total_value, timestamp=datetime.utcnow())
            db.add(snapshot)
            db.commit()

            print(f"Portfolio data updated. Total value: ${total_value:.2f}")

        except Exception as e:
            print(f"Error updating portfolio data: {e}")
            db.rollback()
        finally:
            db.close()

    def start(self):
        """Start the scheduler."""
        # Schedule hourly updates
        self.scheduler.add_job(
            self.update_portfolio_data,
            trigger=CronTrigger(minute=30),  # Run at the top of every hour
            id="update_portfolio",
            name="Update portfolio data",
            replace_existing=True,
        )
        self.scheduler.start()
        print("Scheduler started. Updates will run hourly.")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()

