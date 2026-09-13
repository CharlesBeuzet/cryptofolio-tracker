# Troubleshooting

## Common issues

| Symptom | What to try |
|---------|-------------|
| **Database not found** | Run the backend once to create `portfolio.db`, or `touch data/portfolio.db` before Docker so the mount is a file, not a directory. |
| **Connection errors** | Check API keys / passphrases in **Settings → Connections** or in `config.yaml` (Docker: `data/config.yaml`). Prefer read-only keys. |
| **Settings save failed** | Read the mutation / UI error message. Invalid required fields (e.g. missing Ethereum RPC `hostname`) are rejected before write. |
| **Keys changed but sync still fails** | Save in Settings again (triggers connector reload), or restart the backend. Confirm the exchange is reachable from the host. |
| **No data showing** | Wait for the hourly scheduler, or restart the backend to force a sync. Confirm connectors are declared and configured. |
| **Intermittent OKX / exchange network errors** | Each sync creates fresh connector sessions and retries once on transient failures. If errors persist, check API hostname / firewall / geo-blocks. |
| **CORS errors (local)** | Backend on port **8000**, frontend on **5173**. |
| **Empty Docker UI** | Ensure `data/config.yaml` is filled in and `data/portfolio.db` is a file mount. |

## Performance on Raspberry Pi 5

The stack is intentionally light for single-board hosts:

- SQLite (no separate database server)
- Lean Python / Node dependencies
- Batched exchange fetches where possible
- Frontend code splitting
- Hourly updates to stay within API rate limits
- Fresh connectors per sync to avoid stale keep-alive sockets after idle hours

Prefer building the Docker image **on the Pi** rather than cross-building with QEMU from another architecture.

---

← [Docs hub](README.md) · [Installation](installation.md) · [Settings](settings.md) · [Usage](usage.md)
