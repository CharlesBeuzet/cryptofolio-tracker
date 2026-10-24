# Configuration

Credentials live in `settings/config.yaml` (create from `config.example.yaml`).

For Docker on a Pi, edit `data/config.yaml` instead — that file is bind-mounted into the container.

**Preferred:** after the app is running, use **Settings → Connections** in the UI. See [Settings](settings.md). You can still edit the YAML file directly if you prefer.

## What you can configure

| Section | Fields |
|---------|--------|
| **Binance** | `api_key`, `api_secret` (optional `sandbox`) |
| **OKX** | `api_key`, `api_secret`, `passphrase` (optional `hostname`, `sandbox`) |
| **Mobula** | `api_key`, `wallets` (one address per entry), `blockchains` (chain slugs) |
| **Coinbase** | Present in `config.example.yaml` for reference — not loadable until a connector ships |

### Mobula example

```yaml
mobula:
  api_key: "YOUR_MOBULA_API_KEY"
  wallets:
    - "YOUR_SOLANA_ADDRESS"
    - "0xYOUR_ETHEREUM_ADDRESS"
  blockchains:
    - solana
    - ethereum
```

Public addresses only — never private keys. Allowed slugs: `ethereum`, `base`, `arbitrum`, `polygon`, `avalanche`, `bnb`, `optimism`, `sonic`, `solana`. An empty list makes no Mobula calls. Holdings are stored with the chain slug in `positions.exchange` and the contract in `positions.token_address`.

See `settings/config.example.yaml` and the [settings readme](../settings/readme.md) for the full template. The Settings catalog lists only connectors implemented in the registry (Binance, OKX, Mobula).

## Security

- **Never commit** `config.yaml` (or `data/config.yaml`) — it contains secrets and is gitignored.
- Prefer **read-only** exchange API keys.
- Mobula tracking only needs a **public address** and an API key — never private keys.
- By default the backend runs locally and is not exposed to the public internet; Docker publishes only port 8080 on your LAN.
- The Settings API masks secrets (`••••last4`) and never echoes raw keys back to the client.

---

← [Docs hub](README.md) · [Installation](installation.md) · [Settings](settings.md) · Next: [Usage](usage.md)
