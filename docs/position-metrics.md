# Position metrics

Order-derived analytics for each portfolio position, computed by `PositionAnalyzerService` using the **average-cost** accounting method. All monetary values are in **USD** (via USDT tickers).

## Data model

| Table | Role |
|-------|------|
| `positions` | Exchange mirror: `quantity`, `status`, `symbol`, `exchange` (from balance sync) |
| `position_metrics` | Analytics layer: 1:1 with `positions`, updated from orders + asset prices |
| `orders` | Buy/sell history linked to a position |

Analytics columns (`avg_entry_price`, `pnl`, `pnl_percent`) were removed from `positions` and live exclusively in `position_metrics`.

## Update triggers

Metrics are refreshed:

1. **After new orders** are synced — incremental update from the last processed order watermark.
2. **After asset prices** change — unrealised and total PnL are recomputed for open positions.
3. **On backfill** — full replay of order history when metrics are missing.

## Persisted metrics

### Prices

| Field | Description |
|-------|-------------|
| `avg_entry_price` | Weighted average buy price for remaining holdings. Updated on each buy; unchanged on sell (average-cost rule). |
| `avg_exit_price` | Weighted average sell price across all sells. `null` until the first sell. |
| `break_even_price` | Price at which remaining holdings break even. Equals `avg_entry_price` while quantity > 0. |

### PnL (USD + signed %)

Each PnL metric is stored as a dollar amount and a signed percentage (`+` gain, `-` loss).

| Field | USD formula | % formula |
|-------|-------------|-----------|
| `realised_pnl` | Sum of `(sell_price − avg_entry) × sell_qty` on each sell | `realised_pnl / total_buy_cost × 100` |
| `unrealised_pnl` | `holding_value − (avg_entry_price × order_derived_qty)` | `(current_price / avg_entry_price − 1) × 100` |
| `total_pnl` | `realised_pnl + unrealised_pnl` | `total_pnl / total_buy_cost × 100` |

When fully exited (`order_derived_qty = 0`): `unrealised_pnl = 0`, `realised_pnl = total_pnl`.

### Capital and quantities

| Field | Description |
|-------|-------------|
| `holding_value` | `order_derived_qty × current_price` — market value of order-derived holdings |
| `order_derived_qty` | `total_buy_qty − total_sell_qty` — quantity implied by order history |
| `total_buy_qty` | Sum of buy order quantities |
| `total_buy_cost` | Sum of buy order values (`qty × price`) |
| `total_sell_qty` | Sum of sell order quantities |
| `total_sell_proceeds` | Sum of sell order values (`qty × price`) |

### Derived (computed at read time, not stored)

| Field | Formula | Notes |
|-------|---------|-------|
| `cost_basis` | `avg_entry_price × order_derived_qty` | Remaining book cost of unsold units |
| `cash_in_trade` | `total_buy_cost − total_sell_proceeds` | Net capital deployed minus proceeds withdrawn. When fully exited after a **loss**, this stays **positive** (e.g. bought $1,000, sold $800 → +$200). After a **profit**, it can be **negative**. |

## Incremental update rules

### Buy (`qty`, `price`)

```
total_buy_cost  += qty × price
order_derived_qty += qty
avg_entry_price = (old_avg × old_qty + qty × price) / new_qty
```

### Sell (`qty`, `price`)

```
realised_pnl    += (price − avg_entry_price) × qty   # avg before qty reduction
total_sell_proceeds += qty × price
order_derived_qty -= qty
avg_exit_price  = total_sell_proceeds / total_sell_qty
# avg_entry_price unchanged (average-cost)
```

### Price refresh (`current_price`)

```
holding_value       = order_derived_qty × current_price
unrealised_pnl      = holding_value − avg_entry_price × order_derived_qty
total_pnl           = realised_pnl + unrealised_pnl
# + recompute all % fields
```

## Reconciliation

If `order_derived_qty` diverges from `positions.quantity` (exchange balance), a warning is logged. Balance quantity is the source of truth for holdings; order-derived quantity reflects trade history completeness.

## GraphQL

- `Position.metrics` — full `PositionMetricsType` with all persisted and derived fields.
- Legacy fields on `Position` for backward compatibility:
  - `avgEntryPrice` ← `metrics.avg_entry_price`
  - `pnl` / `pnlPercent` ← `metrics.unrealised_pnl` / `metrics.unrealised_pnl_percent`

## Files

| File | Purpose |
|------|---------|
| `backend/src/models/database.py` | `PositionMetrics` model |
| `backend/src/services/analyzer.py` | Incremental computation engine |
| `backend/src/services/metrics_helpers.py` | Derived metric helpers |
| `backend/src/services/orders.py` | Triggers analyzer after order sync |
| `backend/src/services/scheduler.py` | Backfill + price refresh after each sync cycle |

## Existing databases

`init_db()` creates any missing tables (including `position_metrics`) via SQLAlchemy `create_all`. New installs get the slim `positions` schema directly from the ORM models.

If an old database still has legacy columns on `positions` (`avg_entry_price`, `pnl`, `pnl_percent`), delete `portfolio.db` in development and re-sync, or rebuild that table manually.

After schema is correct, the scheduler backfills metrics from order history on the next sync cycle.

---

← [Docs hub](README.md) · [Features](features.md)
