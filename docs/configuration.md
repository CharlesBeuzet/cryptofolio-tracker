# Configuration

Credentials live in `settings/config.yaml` (create from `config.example.yaml`).

For Docker on a Pi, edit `data/config.yaml` instead — that file is bind-mounted into the container.

**Preferred:** after the app is running, use **Settings → Connections** in the UI. See [Settings](settings.md). You can still edit the YAML file directly if you prefer.

## What you can configure

| Section | Fields |
|---------|--------|
| **Binance** | `api_key`, `api_secret` (optional `sandbox`) |
| **OKX** | `api_key`, `api_secret`, `passphrase` (optional `hostname`, `sandbox`) |
| **Ethereum** | `hostname` (JSON-RPC URL), `address` (public wallet) |
| **Zerion (EVM)** | `hostname` (Zerion API base, default `https://api.zerion.io`), `address` (public EVM wallet), `api_key`; optional `chain_ids` |
| **Coinbase** | Present in `config.example.yaml` for reference — not loadable until a connector ships |

### Ethereum example

```yaml
ethereum:
  hostname: "https://eth.llamarpc.com"
  address: "0xYourEthereumAddressHere"
```

Only a public address and RPC endpoint are required — never private keys. Token contracts are not listed manually in config.

### Zerion / EVM example

```yaml
zerion:
  hostname: "https://api.zerion.io"
  address: "0xYourEthereumAddressHere"
  api_key: "your_zerion_api_key_here"
  # chain_ids: "ethereum,base,arbitrum"   # optional filter
```

The connector pulls token balances from Zerion fungible positions, USD quotes from those positions, synthetic buy/sell orders from wallet transactions (for cost-basis tracking), and chart history from CoinGecko. No private keys.

See `settings/config.example.yaml` and the [settings readme](../settings/readme.md) for the full template. The Settings catalog lists only connectors implemented in the registry (Binance, OKX, Ethereum, Zerion today).

## Security

- **Never commit** `config.yaml` (or `data/config.yaml`) — it contains secrets and is gitignored.
- Prefer **read-only** exchange API keys.
- Hot wallet tracking only needs a **public address** — never private keys.
- By default the backend runs locally and is not exposed to the public internet; Docker publishes only port 8080 on your LAN.
- The Settings API masks secrets (`••••last4`) and never echoes raw keys back to the client.

---

← [Docs hub](README.md) · [Installation](installation.md) · [Settings](settings.md) · Next: [Usage](usage.md)
