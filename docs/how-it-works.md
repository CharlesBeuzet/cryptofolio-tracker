# How it works

## Architecture

```
Exchanges / wallets          Local machine
┌─────────────────┐          ┌──────────────────────────────────┐
│ Binance / OKX / │  ccxt    │  Connectors (scheduled hourly)   │
│ Ethereum RPC    │  web3    │         ↓                        │
└─────────────────┘          │  SQLite (portfolio.db)           │
                             │         ↓                        │
                             │  FastAPI + GraphQL  →  React UI  │
                             └──────────────────────────────────┘
```

1. **Connectors** fetch balances, orders, and wallet holdings on a schedule.
2. Data is persisted in a local **SQLite** database (`portfolio.db` at the repo root).
3. **GraphQL** resolvers expose portfolio, positions, orders, and related data.
4. The **React** frontend queries GraphQL and renders overview, positions, performance, and Settings.

Portfolio balances and orders arrive via the scheduler and connectors. GraphQL **mutations** exist for user intent only: saving connector config and managing conviction tags.

## Technology stack

### Backend

- Python 3.11+
- FastAPI with Strawberry GraphQL
- SQLite
- ccxt for exchange APIs
- web3.py for blockchain wallet queries
- APScheduler for hourly sync

### Frontend

- React 18 with TypeScript
- Vite
- Tailwind CSS (SILLAGE design system)
- Apollo Client for GraphQL
- Recharts for charts

## Project structure

```
cryptofolio-tracker/
├── backend/
│   ├── src/
│   │   ├── connectors/     # Exchange and wallet connectors + registry
│   │   ├── graphql/        # Schema and resolvers
│   │   ├── models/         # SQLAlchemy / SQLite models
│   │   ├── services/       # Sync, valuation, config_settings, tags, analytics
│   │   ├── runtime.py      # Config-reload hook for the running process
│   │   └── main.py         # FastAPI entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── graphql/
│   │   ├── pages/
│   │   └── App.tsx
│   └── package.json
├── settings/
│   ├── config.example.yaml
│   └── config.yaml         # Local secrets (gitignored)
├── docs/                   # This documentation
├── docker-compose.yml
└── Dockerfile
```

## Data flow (summary)

1. On startup (and every hour), the scheduler loads **fresh** connector instances for that run, then syncs balances and orders (with a light retry on transient network errors).
2. Rows update in `positions`, `orders`, and related tables. Balance sync preserves `tag_id` on positions.
3. Position analytics refresh in `position_metrics` (see [Position metrics](position-metrics.md)).
4. Saving Settings writes `config.yaml`, clears the config cache, and reloads connectors without restarting the process (see [Settings](settings.md)).
5. The UI reads the latest state through GraphQL.

### Point of attention — `since` filters creation time, not fill time

Exchange order-history APIs that accept a time cursor (`since` / `startTime` / `begin`) almost always filter on **order creation time** (`cTime`, Binance `time`), **not** fill / completion time (`fTime`, Binance `updateTime` / `lastTradeTimestamp`).

The hourly scheduler still computes `since` from `max(executed_at) − 2h` (fill time). Passing that cursor into a creation-time filter drops limits that were placed earlier and filled later.

| Venue | Do **not** use for incremental fills | Use instead |
|-------|--------------------------------------|-------------|
| **OKX** | `GET /api/v5/trade/orders-history` with `begin` / ccxt `since` (cTime) | Same endpoint **without** `begin` — orders *completed* in the last 7 days |
| **Binance** | `GET /api/v3/allOrders` (`fetch_closed_orders`) with `startTime` (cTime) | `GET /api/v3/myTrades` (`fetch_my_trades`) — `startTime` is fill time — then `GET /api/v3/order` (`fetch_order`) for FILLED status |

Do not widen `since` to the oldest `cTime` on the pair: a GTC limit can stay open for years and would replay unbounded history.

Credentials stay on-premise in `settings/config.yaml` (or the Docker-mounted `data/config.yaml`).

More detail: [backend readme](../backend/readme.md) · [frontend readme](../frontend/readme.md)

---

← [Docs hub](README.md) · [Features](features.md) · Next: [Installation](installation.md)
