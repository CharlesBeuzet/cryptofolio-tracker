# Troubleshooting

## Common issues

| Symptom | What to try |
|---------|-------------|
| **Database not found** | Run the backend once to create `portfolio.db`, or `touch data/portfolio.db` before Docker so the mount is a file, not a directory. |
| **Connection errors** | Check API keys / passphrases in `config.yaml` (or `data/config.yaml` for Docker). |
| **No data showing** | Wait for the hourly scheduler, or restart the backend to force a sync. Confirm credentials and that exchanges are reachable. |
| **CORS errors (local)** | Backend on port **8000**, frontend on **5173**. |
| **Empty Docker UI** | Ensure `data/config.yaml` is filled in and `data/portfolio.db` is a file mount. |

## Performance on Raspberry Pi 5

The stack is intentionally light for single-board hosts:

- SQLite (no separate database server)
- Lean Python / Node dependencies
- Batched exchange fetches where possible
- Frontend code splitting
- Hourly updates to stay within API rate limits

Prefer building the Docker image **on the Pi** rather than cross-building with QEMU from another architecture.

---

← [Docs hub](README.md) · [Installation](installation.md) · [Usage](usage.md)
