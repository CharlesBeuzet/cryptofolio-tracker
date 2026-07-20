# How it works

## Architecture

```
Exchanges / wallets          Local machine
┌─────────────────┐          ┌──────────────────────────────────┐
│ Binance / OKX / │  ccxt    │  Connectors (scheduled hourly)   │
│ Coinbase        │ ───────► │         ↓                        │
│ Ethereum RPC    │  web3    │  SQLite (portfolio.db)           │
└─────────────────┘          │         ↓                        │
                             │  FastAPI + GraphQL  →  React UI  │
                             └──────────────────────────────────┘
```

1. **Connectors** fetch balances, orders, and wallet holdings on a schedule.
2. Data is persisted in a local **SQLite** database (`portfolio.db` at the repo root).
3. **GraphQL** resolvers expose portfolio, positions, orders, and related data.
4. The **React** frontend queries GraphQL and renders overview, positions, and performance views.

There are no GraphQL mutations for portfolio data: values arrive via the scheduler and connectors.

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
│   │   ├── connectors/     # Exchange and wallet connectors
│   │   ├── graphql/        # Schema and resolvers
│   │   ├── models/         # SQLAlchemy / SQLite models
│   │   ├── services/       # Sync, valuation, position analytics
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

1. On startup (and every hour), the scheduler runs connectors.
2. Balances and orders update `positions`, `orders`, and related tables.
3. Position analytics refresh in `position_metrics` (see [Position metrics](position-metrics.md)).
4. The UI reads the latest state through GraphQL.

Credentials stay on-premise in `settings/config.yaml` (or the Docker-mounted `data/config.yaml`).

More detail: [backend readme](../backend/readme.md) · [frontend readme](../frontend/readme.md)

---

← [Docs hub](README.md) · [Features](features.md) · Next: [Installation](installation.md)
