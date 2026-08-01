# Features

Crypto Portfolio Tracker aggregates your crypto holdings and turns them into a single, private dashboard.

## Portfolio overview

- Total portfolio value (NAV)
- Today's P&L
- Asset distribution (allocation)
- One row per asset across venues (venue chips deep-link to each exchange position)

## Performance analysis

- Portfolio value evolution over time
- Comparison against Bitcoin (BTC) as a benchmark

## Position details

- Per-position charts and valuation
- Consolidated **asset** page (`/asset/:symbol`) with multi-venue order history for open venues
- Order history for each venue position
- Average-cost analytics: entry / exit, realised and unrealised P&L
- Duration / “First bought” derived from the earliest buy order fill (falls back to position open date)

See [Position metrics](position-metrics.md) for formulas and the data model.

## Conviction tags

Label each open position (asset × exchange) with a user-defined thesis tag — for example the same coin on two venues under different theses. Tags appear on Overview / Position detail chips, and Theses adds a **By tag** grouping alongside **By venue**.

See [Position tags](position-tags.md).

## Multi-source tracking

Data is pulled and merged from:

- **Binance**
- **OKX**
- **Ethereum** hot wallets (public address + RPC hostname)

Coinbase remains in the example YAML for reference but is not in the Settings add-connector catalog until a connector exists.

## Automatic updates

Connectors sync balances and orders on an hourly schedule so the dashboard stays current without manual refreshes. Each sync run creates fresh connector sessions (with a light retry) to avoid stale HTTP keep-alive failures on long-running hosts.

## Self-hosted UI

React dashboard (SILLAGE design) with:

| Section | What it shows |
|---------|----------------|
| Overview | NAV chart, asset-grouped positions, allocation |
| Asset detail | Consolidated chart, P&L, orders across open venues |
| Position detail | Price chart, P&L panel, order history for one venue |
| Fiat deposits | On-ramp deposits vs NAV |
| Performance (Theses) | Groups by venue and by conviction tag |
| Settings | Connections editor and tag catalog / assignment |

Dark and light themes are supported. On phones the sidebar becomes a drawer; from tablet width up it stays persistent.

---

← [Docs hub](README.md) · Next: [How it works](how-it-works.md)
