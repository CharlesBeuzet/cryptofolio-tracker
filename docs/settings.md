# Settings

The **Settings** page (`/settings`, §5) lets you manage connectors and conviction tags for this local instance without editing YAML by hand.

## Tabs

| Tab | Purpose |
|-----|---------|
| **Connections** | Declare which exchanges / wallets to sync; edit credentials |
| **Tags** | Create conviction tags and assign them to open positions |

Tag data model and mutations are documented in [Position tags](position-tags.md).

## Connections

Active connectors appear as collapsed cards (name + green **Active**). Click a card to expand and edit. Use **+ Add connector** to pick from the project catalog.

### Catalog (addable today)

| Connector | Required fields |
|-----------|-----------------|
| **Binance** | `api_key`, `api_secret` |
| **OKX** | `api_key`, `api_secret`, `passphrase` (optional `hostname` for regional API) |
| **Ethereum** | public `address` + RPC `hostname` |
| **Zerion (EVM)** | public EVM `address` + Zerion API `hostname` + `api_key`; optional YAML `chain_ids` |

Coinbase may still appear in `config.example.yaml` for reference, but it is **not** in the Settings catalog until a connector is implemented.

### Secrets

- The API never returns raw secrets. Fields show a masked hint (`••••` + last 4 characters) when set.
- Leaving a secret field **blank** on save keeps the existing value.
- There is no dedicated “clear secret” action yet (blank ≠ delete).

### Save behaviour

1. Settings writes `settings/config.yaml` atomically (or the Docker-mounted `data/config.yaml`).
2. The config cache is cleared.
3. Connectors reload in-process — no backend restart required.

Removing a connector from the UI and saving deletes that section from the YAML.

## Ethereum wallet shape

```yaml
ethereum:
  hostname: "https://eth.llamarpc.com"   # JSON-RPC endpoint (required)
  address: "0xYourEthereumAddressHere"  # public address (required)
```

- No private keys.
- No manual token contract list — token discovery is handled by the connector path when implemented.
- Free public RPCs work to start; a dedicated RPC is more reliable for production use.

## Zerion / EVM wallet shape

```yaml
zerion:
  hostname: "https://api.zerion.io"       # Zerion REST API base (required)
  address: "0xYourEthereumAddressHere"  # public EVM address (required)
  api_key: "zk_..."                       # dashboard key (required)
  # chain_ids: "ethereum,base,arbitrum"   # optional filter (edit YAML)
```

- No private keys. Holdings come from Zerion `positions` (`only_simple`); portfolio is used for connectivity checks.
- Wallet transactions become synthetic orders (quantity, USD price, mined time) so average entry can be reconstructed.
- Chart history for Zerion positions uses CoinGecko (not exchange OHLCV).
- Settings UI shows address, hostname, and API key; add `chain_ids` in YAML to limit chains.

## GraphQL

**Query**

- `appConfig` — masked view of active connectors and the available catalog

**Mutation**

- `updateAppConfig(exchanges, replaceExchanges)` — persist connector changes

When `replaceExchanges` is `true`, the declared list becomes the full set of exchange/wallet sections in YAML (the Connections UI uses this). Secret fields that are `null` / omitted are left unchanged.

Example (partial — leave secrets blank to keep them):

```graphql
mutation {
  updateAppConfig(
    replaceExchanges: true
    exchanges: [
      { name: "binance", apiKey: null, apiSecret: null }
      {
        name: "ethereum"
        address: "0xYourEthereumAddressHere"
        hostname: "https://eth.llamarpc.com"
      }
    ]
  ) {
    success
    message
    config {
      exchanges {
        name
        label
        configured
        apiKey { isSet hint }
      }
    }
  }
}
```

## Security model

- No auth layer: the endpoint inherits the existing localhost / LAN trust model.
- Prefer **read-only** exchange API keys.
- Never commit `config.yaml` (gitignored).

See also [Configuration](configuration.md) for file-based setup and security notes.

---

← [Docs hub](README.md) · [Configuration](configuration.md) · [Position tags](position-tags.md)
