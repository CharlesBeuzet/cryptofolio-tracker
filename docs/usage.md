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

5. Optional: open **Settings → Connections** to add or edit connectors without restarting the process.

## Docker (Raspberry Pi)

After `docker compose up -d --build`, open `http://<pi-ip>:8080`. Data and config live under `./data/` on the host. Credentials can also be edited under **Settings → Connections**.

## GraphQL API

Endpoint: `http://localhost:8000/graphql` (or `/graphql` behind nginx in Docker).

You can use GraphQL Playground or any GraphQL client.

### Portfolio query

Balances and orders are filled by connectors — there are **no mutations to invent portfolio balances**. Example:

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
      exchange
      tag { id name }
    }
  }
}
```

### Mutations (user intent)

| Area | Operations | Docs |
|------|------------|------|
| Config | `appConfig` query, `updateAppConfig` mutation | [Settings](settings.md) |
| Tags | `createTag`, `updateTag`, `deleteTag`, `setPositionTag` | [Position tags](position-tags.md) |

---

← [Docs hub](README.md) · [Configuration](configuration.md) · [Settings](settings.md) · [Troubleshooting](troubleshooting.md)
