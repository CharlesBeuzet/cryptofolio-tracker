# AGENTS.md

## Cursor Cloud specific instructions

Crypto Portfolio Tracker: a Python/FastAPI + Strawberry GraphQL backend (SQLite) and a
React/Vite/TypeScript frontend. SQLite is embedded (no DB server). Standard setup/run
commands live in `README.md`; only the non-obvious caveats are captured here.

### Services
- Backend (FastAPI + GraphQL + APScheduler), port `8000`. Run from `backend/`:
  `./venv/bin/python -m src.main`. The Python deps live in a venv at `backend/venv`
  (created by the update script). GraphQL at `/graphql`, health at `/health`.
- Frontend (Vite dev server), port `5173`: `cd frontend && npm run dev`. It needs the
  backend running on `8000` (Apollo client + Vite `/graphql` proxy both target `:8000`).

### Non-obvious caveats
- The SQLite DB file is created at the **repo root** (`/workspace/portfolio.db`), not in
  `backend/`, because `DATABASE_PATH` resolves four levels up from `models/database.py`.
- Backend startup runs an **immediate portfolio sync inside the FastAPI lifespan**, which
  calls external exchange/RPC APIs. In this environment Binance is geo-blocked (HTTP `451`)
  and these errors are caught/logged (non-fatal), but "Application startup complete" can
  take ~20-30s. Wait for it before hitting the API.
- `settings/config.yaml` (copied from `config.example.yaml`) holds exchange/wallet
  credentials. With placeholder/missing credentials the app boots fine but the dashboard
  shows empty/zero data. There are **no GraphQL mutations**; data only arrives via the
  scheduler connectors. To demo the UI without real keys, seed the DB directly (Asset +
  Position + Order + PortfolioSnapshot via `src.models.database.SessionLocal`).
- `cd frontend && npm run lint` currently fails on a **pre-existing** `no-explicit-any`
  error in `src/components/charts/PositionChart.tsx` (ESLint runs with
  `--max-warnings 0`). This is a code issue, not an environment problem.
