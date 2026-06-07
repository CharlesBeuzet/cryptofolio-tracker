"""Scheduler service for periodic data updates."""
import yaml
from pathlib import Path
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..models.database import SessionLocal
from ..connectors.base import BaseConnector
from ..connectors.binance import BinanceConnector
from .fiat_deposits import FiatDepositService
from .assets import AssetsService
from .orders import OrderService
from .analyzer import PositionAnalyzerService


class DataUpdateScheduler:
    """Scheduler for updating portfolio data from all connectors."""

    def __init__(self, config_path: str = None):
        if config_path is None:
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

        if config.get("binance"):
            try:
                self.connectors.append(BinanceConnector(config["binance"]))
                print("Binance connector initialized")
            except Exception as e:
                print(f"Failed to initialize Binance connector: {e}")

    async def update_portfolio_data(self):
        """Update portfolio data from all connectors."""
        print("Starting portfolio data update...")
        db = SessionLocal()
        try:
            assets_svc = AssetsService(db)
            for connector in self.connectors:
                try:
                    result = await assets_svc.sync_from_connector(connector)
                    if any(result.values()):
                        print(
                            f"Synced from {connector.name}: "
                            f"{result['assets_updated']} asset(s), "
                            f"{result['positions_opened']} opened, "
                            f"{result['positions_closed']} closed."
                        )
                except Exception as e:
                    print(f"Error syncing assets from {connector.name}: {e}")
                    db.rollback()

            fiat_svc = FiatDepositService(db)
            for connector in self.connectors:
                try:
                    n = fiat_svc.sync_deposits_from_connector(connector)
                    if n:
                        print(f"Synced {n} new fiat deposit record(s) from {connector.name}.")
                except Exception as e:
                    print(f"Error syncing fiat deposits from {connector.name}: {e}")
                    db.rollback()

            order_svc = OrderService(db)
            for connector in self.connectors:
                symbols = order_svc.get_symbols_for_connector(connector)
                for symbol in symbols:
                    try:
                        n = order_svc.sync_orders_from_connector(connector, symbol)
                        if n:
                            print(
                                f"Synced {n} new order(s) for {symbol} from {connector.name}."
                            )
                    except Exception as e:
                        print(
                            f"Error syncing orders for {symbol} from {connector.name}: {e}"
                        )
                        db.rollback()

            analyzer = PositionAnalyzerService(db)
            try:
                backfilled = analyzer.backfill_if_missing()
                if backfilled:
                    print(f"Backfilled metrics for {backfilled} position(s).")
            except Exception as e:
                print(f"Error backfilling position metrics: {e}")
                db.rollback()

            try:
                refreshed = analyzer.refresh_all_open_prices()
                if refreshed:
                    print(f"Refreshed market metrics for {refreshed} open position(s).")
            except Exception as e:
                print(f"Error refreshing position market metrics: {e}")
                db.rollback()

        except Exception as e:
            print(f"Error updating portfolio data: {e}")
            db.rollback()
        finally:
            db.close()

    def start(self):
        """Start the scheduler."""
        self.scheduler.add_job(
            self.update_portfolio_data,
            trigger=CronTrigger(minute=30),
            id="update_portfolio",
            name="Update portfolio data",
            replace_existing=True,
        )
        self.scheduler.start()
        print("Scheduler started. Updates will run hourly.")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
