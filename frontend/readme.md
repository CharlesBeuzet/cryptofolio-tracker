# Frontend

React + TypeScript + Vite application for the SILLAGE portfolio tracker UI.

## Design

The visual reference lives in `design-reference/Sillage.html`. The app uses:

- **SILLAGE** sidebar layout with §1–§5 navigation
- IBM Plex Mono for labels and data, Spectral for headings
- Dark and light themes (toggle in the top bar)
- Tailwind CSS with design tokens in `src/index.css` and `tailwind.config.js`

## Pages

| Route | Section | Description |
|-------|---------|-------------|
| `/` | §1 Overview | NAV chart, asset-grouped positions, allocation donut |
| `/asset/:symbol` | §2 Asset detail | Consolidated chart, P&L, orders across open venues |
| `/position/:id` | §2 Position detail | Price chart, P&L panel, order history for one venue |
| `/fiat-deposits` | §3 On-ramp | Deposits vs NAV chart, deposit ledger |
| `/performance` | §4 Theses | Performance grouped by venue and by conviction tag |
| `/settings` | §5 Settings | Connections editor and tag catalog / assignment |

## Run locally

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:5173` and proxies GraphQL to the backend on port `8000`.

## Scripts

- `npm run dev` — development server
- `npm run build` — production build
- `npm run lint` — ESLint
