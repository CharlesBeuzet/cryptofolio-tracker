"""Scheduler service for periodic data updates."""
import asyncio
from pathlib import Path
from typing import Any, Callable, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..connectors.base import BaseConnector
from ..connectors.registry import load_connectors
from ..models.database import SessionLocal
from .analyzer import PositionAnalyzerService
from .assets import AssetsService
from .fiat_deposits import FiatDepositService
from .orders import OrderService
from .portfolio import PortfolioService

# Light retry for transient connector/network blips (e.g. first call after idle).
_SYNC_ATTEMPTS = 2
_SYNC_RETRY_DELAY_S = 0.5


class DataUpdateScheduler:
    """Scheduler for updating portfolio data from all connectors."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
            config_path = str(BASE_DIR / "settings" / "config.yaml")
        self.config_path = config_path
        self.scheduler = AsyncIOScheduler()
        self.reload_connectors()

    def reload_connectors(self) -> List[BaseConnector]:
        """Re-read config.yaml and instantiate connectors (fresh HTTP sessions)."""
        loaded = load_connectors(self.config_path)
        if loaded:
            for connector in loaded:
                print(f"{connector.name} connector initialized")
        else:
            print("No exchange connectors configured")
        return loaded

    async def _with_retry(self, label: str, fn: Callable[[], Any]) -> Any:
        """Run fn (sync or async) with one light retry; log type + message on failure."""
        last_exc: Optional[BaseException] = None
        for attempt in range(1, _SYNC_ATTEMPTS + 1):
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as e:
                last_exc = e
                print(
                    f"WARNING: {label} failed "
                    f"(attempt {attempt}/{_SYNC_ATTEMPTS}): "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < _SYNC_ATTEMPTS:
                    await asyncio.sleep(_SYNC_RETRY_DELAY_S)
                    continue
                print(f"ERROR: {label} giving up after {_SYNC_ATTEMPTS} attempt(s)")
                raise
        assert last_exc is not None
        raise last_exc

    async def update_portfolio_data(self):
        """Update portfolio data from all connectors."""
        print("Starting portfolio data update...")
        connectors = self.reload_connectors()
        db = SessionLocal()
        try:
            assets_svc = AssetsService(db)
            for connector in connectors:
                try:
                    result = await self._with_retry(
                        f"sync assets from {connector.name}",
                        lambda c=connector: assets_svc.sync_from_connector(c),
                    )
                    if any(result.values()):
                        print(
                            f"Synced from {connector.name}: "
                            f"{result['assets_updated']} asset(s), "
                            f"{result['positions_opened']} opened, "
                            f"{result['positions_closed']} closed."
                        )
                except Exception as e:
                    print(
                        f"Error syncing assets from {connector.name}: "
                        f"{type(e).__name__}: {e}"
                    )
                    db.rollback()

            fiat_svc = FiatDepositService(db)
            for connector in connectors:
                try:
                    n = await self._with_retry(
                        f"sync fiat deposits from {connector.name}",
                        lambda c=connector: fiat_svc.sync_deposits_from_connector(c),
                    )
                    if n:
                        print(
                            f"Synced {n} new fiat deposit record(s) from {connector.name}."
                        )
                except Exception as e:
                    print(
                        f"Error syncing fiat deposits from {connector.name}: "
                        f"{type(e).__name__}: {e}"
                    )
                    db.rollback()

            order_svc = OrderService(db)
            for connector in connectors:
                symbols = order_svc.get_symbols_for_connector(connector)
                for symbol in symbols:
                    try:
                        n = await self._with_retry(
                            f"sync orders for {symbol} from {connector.name}",
                            lambda c=connector, s=symbol: order_svc.sync_orders_from_connector(
                                c, s
                            ),
                        )
                        if n:
                            print(
                                f"Synced {n} new order(s) for {symbol} "
                                f"from {connector.name}."
                            )
                    except Exception as e:
                        print(
                            f"Error syncing orders for {symbol} from {connector.name}: "
                            f"{type(e).__name__}: {e}"
                        )
                        db.rollback()

            analyzer = PositionAnalyzerService(db)
            try:
                backfilled = await self._with_retry(
                    "backfill position metrics",
                    analyzer.backfill_if_missing,
                )
                if backfilled:
                    print(f"Backfilled metrics for {backfilled} position(s).")
            except Exception as e:
                print(
                    f"Error backfilling position metrics: {type(e).__name__}: {e}"
                )
                db.rollback()

            try:
                refreshed = await self._with_retry(
                    "refresh open position prices",
                    analyzer.refresh_all_open_prices,
                )
                if refreshed:
                    print(f"Refreshed market metrics for {refreshed} open position(s).")
            except Exception as e:
                print(
                    f"Error refreshing position market metrics: "
                    f"{type(e).__name__}: {e}"
                )
                db.rollback()

        except Exception as e:
            print(f"Error updating portfolio data: {type(e).__name__}: {e}")
            db.rollback()
        finally:
            db.close()

    async def record_portfolio_snapshot(self):
        """Refresh prices and persist a portfolio value snapshot."""
        print("Recording portfolio snapshot...")
        db = SessionLocal()
        try:
            analyzer = PositionAnalyzerService(db)
            try:
                refreshed = await self._with_retry(
                    "refresh prices before snapshot",
                    analyzer.refresh_all_open_prices,
                )
                if refreshed:
                    print(
                        f"Refreshed market metrics for {refreshed} open position(s) "
                        "before snapshot."
                    )
            except Exception as e:
                print(
                    f"Error refreshing prices before snapshot: "
                    f"{type(e).__name__}: {e}"
                )
                db.rollback()

            snapshot = PortfolioService(db).record_snapshot()
            if snapshot:
                print(
                    f"Portfolio snapshot recorded: "
                    f"${snapshot.total_value:,.2f} at {snapshot.timestamp.isoformat()}"
                )
        except Exception as e:
            print(f"Error recording portfolio snapshot: {type(e).__name__}: {e}")
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
        self.scheduler.add_job(
            self.record_portfolio_snapshot,
            trigger=CronTrigger(minute=35, hour="0,6,12,18"),
            id="portfolio_snapshot",
            name="Record portfolio snapshot",
            replace_existing=True,
        )
        self.scheduler.start()
        print(
            "Scheduler started. Portfolio sync runs hourly; "
            "snapshots run every 6 hours (00:35, 06:35, 12:35, 18:35 UTC). "
            "Connectors are created fresh each sync run."
        )

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
