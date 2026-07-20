# Crypto Portfolio Tracker

**Your entire crypto life — exchanges, wallets, P&L — on a machine you own.**

Stop tabbing between Binance, OKX, Coinbase, and block explorers. Stop trusting a SaaS dashboard with your balances. Run a private portfolio tracker on a Raspberry Pi (or any machine), refresh hourly, and see the full picture in one place.

---

### Why people install it

| | |
|---|---|
| **One view** | Total NAV, today's P&L, allocation, and ranked positions — not five browser tabs. |
| **Your keys stay home** | API secrets live in a local config file. No cloud account. No telemetry. |
| **Built for a Pi** | SQLite, a single Docker container, one published port. Designed for Raspberry Pi 4/5. |
| **Real analytics** | Average-cost entry, realised / unrealised P&L, order history per position. |
| **Multi-source by default** | Binance · OKX · Coinbase · Ethereum hot wallets — aggregated into one portfolio. |

---

### What you get

- **Portfolio overview** — value, daily P&L, distribution, rankings  
- **Performance over time** — NAV evolution with BTC comparison  
- **Position deep-dives** — charts, metrics, and full order history  
- **Hourly sync** — connectors pull balances and orders on a schedule  
- **Self-hosted UI** — React dashboard with dark / light themes  

Want the full list? → **[Features](docs/features.md)**

Curious how the pieces fit together? → **[How it works](docs/how-it-works.md)**

---

### Install in minutes

On a Raspberry Pi with Docker:

```bash
mkdir -p data
cp settings/config.example.yaml data/config.yaml
# edit data/config.yaml with read-only exchange keys + wallet addresses
touch data/portfolio.db
docker compose up -d --build
```

Open `http://<pi-ip>:8080` — you're live.

→ **[Full installation guide](docs/installation.md)** (Docker on Pi · local development)  
→ **[Configuration](docs/configuration.md)** (exchanges, wallets, security)  
→ **[Usage & GraphQL API](docs/usage.md)**

---

### Documentation

| Guide | What you'll find |
|-------|------------------|
| [Features](docs/features.md) | What the product does, page by page |
| [How it works](docs/how-it-works.md) | Architecture, stack, data flow, project layout |
| [Installation](docs/installation.md) | Docker (Pi) and local backend / frontend setup |
| [Configuration](docs/configuration.md) | API keys, wallets, security practices |
| [Usage](docs/usage.md) | Day-to-day use and GraphQL examples |
| [Troubleshooting](docs/troubleshooting.md) | Common fixes and Pi performance tips |
| [Position metrics](docs/position-metrics.md) | Average-cost P&L and analytics model |
| [Docs hub](docs/README.md) | Index of all documentation |

Component notes: [backend](backend/readme.md) · [frontend](frontend/readme.md) · [settings](settings/readme.md)

---

### Stack at a glance

**Backend** — Python · FastAPI · Strawberry GraphQL · SQLite · ccxt · web3.py  

**Frontend** — React · TypeScript · Vite · Tailwind · Apollo · Recharts  

Details in **[How it works](docs/how-it-works.md)**.

---

### Philosophy

Your portfolio data is yours. This app runs where you put it, talks only to the exchanges and RPCs you configure, and stores everything in a local SQLite file. Read-only API keys are enough. Wallet tracking needs public addresses only — never private keys.

---

**Ready?** Start with the **[installation guide](docs/installation.md)**.

Author: Charles Beuzet
