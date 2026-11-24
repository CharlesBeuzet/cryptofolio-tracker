# Settings

This folder holds configuration required to fetch portfolio data from exchanges and wallets.

**Do not commit real credentials to Git.** Copy `config.example.yaml` to `config.yaml` and fill in your keys locally, or edit connectors in the UI under **Settings → Connections** once the app is running.

`config.yaml` is gitignored. An example structure is provided in `config.example.yaml`.

## Shape notes

- **Exchanges** (Binance, OKX): API secrets; prefer read-only keys.
- **Mobula**: `api_key`, public `wallets`, and `blockchains` slugs. No private keys. The chain is stored on each position, not as a separate connector.
- **Coinbase**: still shown in the example file for reference; not addable in Settings until a connector exists.

See [docs/configuration.md](../docs/configuration.md) and [docs/settings.md](../docs/settings.md).
