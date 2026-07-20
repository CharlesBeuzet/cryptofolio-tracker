# Configuration

Edit `settings/config.yaml` (create from `config.example.yaml`) to connect your data sources.

For Docker on a Pi, edit `data/config.yaml` instead — that file is bind-mounted into the container.

## What you can configure

- **Binance** — API key and secret
- **OKX** — API key, secret, and passphrase
- **Coinbase** — API key, secret, and passphrase
- **Hot wallets** — Ethereum addresses and token contracts to track

See `settings/config.example.yaml` and the [settings readme](../settings/readme.md) for the expected shape.

## Security

- **Never commit** `config.yaml` (or `data/config.yaml`) — it contains secrets and is gitignored.
- Prefer **read-only** exchange API keys.
- Hot wallet tracking only needs **public addresses** — never private keys.
- By default the backend runs locally and is not exposed to the public internet; Docker publishes only port 8080 on your LAN.

---

← [Docs hub](README.md) · [Installation](installation.md) · Next: [Usage](usage.md)
