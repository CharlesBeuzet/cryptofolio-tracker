# Usage

## Local development

1. Start the backend (from `backend/`):

```bash
python -m src.main
```

2. Start the frontend (from `frontend/`):

```bash
npm run dev
```

3. Open `http://localhost:5173`

4. The scheduler updates portfolio data every hour. Restarting the backend also triggers a sync on startup.

## Docker (Raspberry Pi)

After `docker compose up -d --build`, open `http://<pi-ip>:8080`. Data and config live under `./data/` on the host.

## GraphQL API

Endpoint: `http://localhost:8000/graphql` (or `/graphql` behind nginx in Docker).

You can use GraphQL Playground or any GraphQL client.

Example query:

```graphql
query {
  portfolio {
    totalValue
    todaysPnl
    positions {
      symbol
      quantity
      value
      pnl
    }
  }
}
```

Portfolio rows are filled by connectors — there are no mutations to invent balances in the API.

---

← [Docs hub](README.md) · [Configuration](configuration.md) · [Troubleshooting](troubleshooting.md)
