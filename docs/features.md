# Features

Crypto Portfolio Tracker aggregates your crypto holdings and turns them into a single, private dashboard.

## Portfolio overview

- Total portfolio value (NAV)
- Today's P&L
- Asset distribution (allocation)
- Position rankings

## Performance analysis

- Portfolio value evolution over time
- Comparison against Bitcoin (BTC) as a benchmark

## Position details

- Per-position charts and valuation
- Order history for each position
- Average-cost analytics: entry / exit, realised and unrealised P&L  

See [Position metrics](position-metrics.md) for formulas and the data model.

## Multi-source tracking

Data is pulled and merged from:

- **Binance**
- **OKX**
- **Coinbase**
- **Hot wallets** (Ethereum addresses and configured token contracts)

## Automatic updates

Connectors sync balances and orders on an hourly schedule so the dashboard stays current without manual refreshes.

## Self-hosted UI

React dashboard (SILLAGE design) with:

| Section | What it shows |
|---------|----------------|
| Overview | NAV chart, positions table, allocation |
| Position detail | Price chart, P&L panel, order history |
| Fiat deposits | On-ramp deposits vs NAV |
| Performance | Performance grouped by venue |

Dark and light themes are supported.

---

← [Docs hub](README.md) · Next: [How it works](how-it-works.md)
