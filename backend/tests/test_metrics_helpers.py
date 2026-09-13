"""Unit tests for derived position metric helpers."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.services.metrics_helpers import cash_in_trade, cost_basis


def _metrics(**kwargs):
    defaults = {
        "avg_entry_price": 0.0,
        "order_derived_qty": 0.0,
        "total_buy_cost": 0.0,
        "total_sell_proceeds": 0.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class CashInTradeTests(unittest.TestCase):
    def test_open_position_is_full_buy_cost(self):
        self.assertEqual(cash_in_trade(_metrics(total_buy_cost=1000.0, total_sell_proceeds=0.0)), 1000.0)

    def test_partial_sell_before_stake_repaid(self):
        self.assertEqual(cash_in_trade(_metrics(total_buy_cost=1000.0, total_sell_proceeds=400.0)), 600.0)

    def test_breakeven_cash_is_zero(self):
        self.assertEqual(cash_in_trade(_metrics(total_buy_cost=1000.0, total_sell_proceeds=1000.0)), 0.0)

    def test_profit_is_capped_at_zero(self):
        self.assertEqual(cash_in_trade(_metrics(total_buy_cost=1000.0, total_sell_proceeds=1200.0)), 0.0)

    def test_loss_on_exit_stays_positive(self):
        self.assertEqual(cash_in_trade(_metrics(total_buy_cost=1000.0, total_sell_proceeds=800.0)), 200.0)


class CostBasisTests(unittest.TestCase):
    def test_remaining_book_cost(self):
        self.assertEqual(cost_basis(_metrics(avg_entry_price=50.0, order_derived_qty=2.0)), 100.0)


if __name__ == "__main__":
    unittest.main()
