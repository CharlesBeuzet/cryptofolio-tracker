"""Fiat deposit records (exchange fiat on-ramps + manual DB rows)."""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.database import FiatDeposit


def _counts_for_summary(amount: float, status: Optional[str], source: str) -> float:
    """Amount included in dashboard totals: successful API deposits and all manual rows."""
    if source == "manual":
        return amount
    if not status:
        return 0.0
    s = status.lower()
    if s in ("successful", "completed", "complete", "success"):
        return amount
    return 0.0


class FiatDepositService:
    """Persist and aggregate fiat injection records."""

    def __init__(self, db: Session):
        self.db = db

    def sync_deposits_from_connector(self, connector: Any, rows: int = 100) -> int:
        """Persist new fiat deposit orders returned by the connector. Returns number of rows inserted."""
        exchange = connector.name
        print(f"Syncing fiat deposits from {connector.name} ...")
        raw = connector.fetch_fiat_deposit_orders_sync(rows=rows)
        added = 0
        for row in raw:
            order_no = row.get("external_order_id")
            if not order_no:
                continue
            exists = (
                self.db.query(FiatDeposit)
                .filter(
                    FiatDeposit.exchange == exchange,
                    FiatDeposit.external_order_id == order_no,
                )
                .first()
            )
            if exists:
                continue
            rec = FiatDeposit(
                exchange=exchange,
                external_order_id=order_no,
                currency=row["currency"],
                amount=row["amount"],
                fee=row.get("fee"),
                status=row.get("status"),
                method=row.get("method"),
                deposited_at=row["deposited_at"],
                source="api_sync",
            )
            self.db.add(rec)
            added += 1
        if added:
            self.db.commit()
        return added

    def get_summary(self) -> Dict:
        """Totals grouped by fiat currency (successful API + all manual)."""
        rows = self.db.query(FiatDeposit).all()
        totals: Dict[str, float] = {}
        counted = 0
        for r in rows:
            inc = _counts_for_summary(r.amount, r.status, r.source)
            if inc <= 0:
                continue
            counted += 1
            totals[r.currency] = totals.get(r.currency, 0.0) + inc
        by_currency = [{"currency": c, "total_amount": round(a, 2)} for c, a in sorted(totals.items())]
        return {"totals_by_currency": by_currency, "included_record_count": counted}

    def list_deposits(self, limit: int = 500) -> List[FiatDeposit]:
        return (
            self.db.query(FiatDeposit)
            .order_by(FiatDeposit.deposited_at.desc())
            .limit(limit)
            .all()
        )
