# Backend

## Responsibilities

- Fetch data from CEXs, hot wallets, and cold-wallet snapshots
- Persist useful data in SQLite
- Serve data to the frontend via GraphQL

## Architecture

Data connectors implement a shared interface. Each provider (Binance, Coinbase, wallet RPC, etc.) is a concrete connector class.

API keys and other authentication values are stored on-premise only to keep credentials local.

## Data flow

1. Connectors run on a schedule and update the database
2. GraphQL resolvers expose portfolio, positions, orders, and fiat deposits to the frontend

## Run locally

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

GraphQL: `http://localhost:8000/graphql`  
Health: `http://localhost:8000/health`
