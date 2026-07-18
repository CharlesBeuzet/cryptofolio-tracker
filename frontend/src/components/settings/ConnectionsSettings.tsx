import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQuery } from '@apollo/client'
import { GET_APP_CONFIG, UPDATE_APP_CONFIG } from '../../graphql/queries'

type SecretField = { isSet: boolean; hint?: string | null }

type ExchangeConfig = {
  name: string
  configured: boolean
  supportsPassphrase: boolean
  sandbox?: boolean | null
  hostname?: string | null
  apiKey: SecretField
  apiSecret: SecretField
  passphrase: SecretField
}

type WalletToken = { address: string; symbol: string; decimals: number }
type WalletAddress = { address: string; chain: string; tokens: WalletToken[] }
type RpcUrl = { chain: string; url: string }

type ExchangeDraft = {
  name: string
  apiKey: string
  apiSecret: string
  passphrase: string
  hostname: string
  sandbox: boolean
}

type StatusMsg = { kind: 'ok' | 'err'; text: string } | null

function titleCase(name: string) {
  return name.charAt(0).toUpperCase() + name.slice(1)
}

export default function ConnectionsSettings() {
  const { data, loading, error, refetch } = useQuery(GET_APP_CONFIG)
  const [updateConfig, { loading: saving }] = useMutation(UPDATE_APP_CONFIG)

  const [exchanges, setExchanges] = useState<ExchangeDraft[]>([])
  const [defaultRpc, setDefaultRpc] = useState('')
  const [rpcUrls, setRpcUrls] = useState<RpcUrl[]>([])
  const [addresses, setAddresses] = useState<WalletAddress[]>([])
  const [status, setStatus] = useState<StatusMsg>(null)
  const [meta, setMeta] = useState<{ exists: boolean; relativePath: string } | null>(null)
  const [serverExchanges, setServerExchanges] = useState<ExchangeConfig[]>([])

  useEffect(() => {
    const cfg = data?.appConfig
    if (!cfg) return

    setMeta({ exists: cfg.exists, relativePath: cfg.relativePath })
    setServerExchanges(cfg.exchanges || [])
    setExchanges(
      (cfg.exchanges || []).map((ex: ExchangeConfig) => ({
        name: ex.name,
        apiKey: '',
        apiSecret: '',
        passphrase: '',
        hostname: ex.hostname || '',
        sandbox: Boolean(ex.sandbox),
      })),
    )
    setDefaultRpc(cfg.hotWallets?.defaultRpc || '')
    setRpcUrls(
      (cfg.hotWallets?.rpcUrls || []).map((r: RpcUrl) => ({
        chain: r.chain,
        url: r.url,
      })),
    )
    setAddresses(
      (cfg.hotWallets?.addresses || []).map((a: WalletAddress) => ({
        address: a.address,
        chain: a.chain,
        tokens: (a.tokens || []).map((t) => ({
          address: t.address,
          symbol: t.symbol,
          decimals: t.decimals,
        })),
      })),
    )
  }, [data])

  const updateExchange = (name: string, patch: Partial<ExchangeDraft>) => {
    setExchanges((prev) => prev.map((ex) => (ex.name === name ? { ...ex, ...patch } : ex)))
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setStatus(null)

    try {
      const result = await updateConfig({
        variables: {
          exchanges: exchanges.map((ex) => ({
            name: ex.name,
            // null = keep existing secret; non-empty string replaces it
            apiKey: ex.apiKey.trim() || null,
            apiSecret: ex.apiSecret.trim() || null,
            passphrase: ex.passphrase.trim() || null,
            // empty string clears optional hostname
            hostname: ex.hostname.trim(),
            sandbox: ex.sandbox,
          })),
          hotWallets: {
            defaultRpc: defaultRpc.trim() || null,
            rpcUrls: rpcUrls.filter((r) => r.chain.trim() && r.url.trim()),
            addresses: addresses
              .filter((a) => a.address.trim())
              .map((a) => ({
                address: a.address.trim(),
                chain: a.chain.trim() || 'ethereum',
                tokens: a.tokens
                  .filter((t) => t.address.trim())
                  .map((t) => ({
                    address: t.address.trim(),
                    symbol: t.symbol.trim(),
                    decimals: Number.isFinite(t.decimals) ? t.decimals : 18,
                  })),
              })),
          },
        },
      })

      const payload = result.data?.updateAppConfig
      if (!payload?.success) {
        setStatus({ kind: 'err', text: payload?.message || 'Save failed' })
        return
      }
      setStatus({ kind: 'ok', text: payload.message })
      await refetch()
      // Clear secret draft fields after a successful save
      setExchanges((prev) =>
        prev.map((ex) => ({ ...ex, apiKey: '', apiSecret: '', passphrase: '' })),
      )
    } catch (err) {
      setStatus({
        kind: 'err',
        text: err instanceof Error ? err.message : 'Save failed',
      })
    }
  }

  if (loading && !data) {
    return (
      <div className="panel text-sillage-soft font-mono text-sm">Loading configuration…</div>
    )
  }

  if (error) {
    return (
      <div className="panel text-sillage-down font-mono text-sm">
        Failed to load config: {error.message}
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <div className="panel">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="lbl">Connections</div>
            <div className="font-serif text-[22px] leading-none mt-2">Connectors declaration</div>
            <p className="cap mt-3 max-w-2xl">
              Read-only exchange API keys and public wallet addresses. Secrets are masked in the UI;
              leave a secret field blank to keep the current value.
            </p>
          </div>
          <span className="chip">{meta?.exists ? 'Configured' : 'Empty'}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {exchanges.map((ex) => {
          const server = serverExchanges.find((s) => s.name === ex.name)
          return (
            <div key={ex.name} className="panel flex flex-col gap-3.5">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="lbl">Exchange</div>
                  <div className="font-serif text-[20px] leading-none mt-1.5">
                    {titleCase(ex.name)}
                  </div>
                </div>
                <span className={`chip ${server?.configured ? 'text-sillage-green border-sillage-green' : ''}`}>
                  {server?.configured ? 'Configured' : 'Empty'}
                </span>
              </div>

              <SecretInput
                label="API key"
                hint={server?.apiKey.hint}
                isSet={Boolean(server?.apiKey.isSet)}
                value={ex.apiKey}
                onChange={(value) => updateExchange(ex.name, { apiKey: value })}
              />
              <SecretInput
                label="API secret"
                hint={server?.apiSecret.hint}
                isSet={Boolean(server?.apiSecret.isSet)}
                value={ex.apiSecret}
                onChange={(value) => updateExchange(ex.name, { apiSecret: value })}
              />
              {server?.supportsPassphrase && (
                <SecretInput
                  label="Passphrase"
                  hint={server?.passphrase.hint}
                  isSet={Boolean(server?.passphrase.isSet)}
                  value={ex.passphrase}
                  onChange={(value) => updateExchange(ex.name, { passphrase: value })}
                />
              )}

              <label className="flex flex-col gap-1.5">
                <span className="lbl">Hostname (optional)</span>
                <input
                  className="field"
                  value={ex.hostname}
                  onChange={(e) => updateExchange(ex.name, { hostname: e.target.value })}
                  placeholder={ex.name === 'okx' ? 'openapi.okx.com' : 'optional'}
                  autoComplete="off"
                />
              </label>

              <label className="flex items-center gap-2.5 font-mono text-[11px] text-sillage-soft cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={ex.sandbox}
                  onChange={(e) => updateExchange(ex.name, { sandbox: e.target.checked })}
                  className="accent-[var(--green)]"
                />
                Sandbox / testnet
              </label>
            </div>
          )
        })}
        {exchanges.length === 0 &&
          ['binance', 'okx', 'coinbase'].map((name) => (
            <div key={name} className="panel text-sillage-soft font-mono text-sm">
              {titleCase(name)} — awaiting schema
            </div>
          ))}
      </div>

      <div className="panel flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="lbl">Wallets</div>
            <div className="font-serif text-[22px] leading-none mt-2">Hot wallets</div>
            <p className="cap mt-2">Public addresses only — never paste a private key.</p>
          </div>
          <button
            type="button"
            className="btn-ghost"
            onClick={() =>
              setAddresses((prev) => [...prev, { address: '', chain: 'ethereum', tokens: [] }])
            }
          >
            + Address
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="lbl">Default RPC</span>
            <input
              className="field"
              value={defaultRpc}
              onChange={(e) => setDefaultRpc(e.target.value)}
              placeholder="https://eth.llamarpc.com"
              autoComplete="off"
            />
          </label>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="lbl">Chain RPC overrides</span>
              <button
                type="button"
                className="btn-ghost text-[10px]"
                onClick={() => setRpcUrls((prev) => [...prev, { chain: '', url: '' }])}
              >
                + RPC
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {rpcUrls.length === 0 && (
                <div className="font-mono text-[11px] text-sillage-soft">None — using default RPC.</div>
              )}
              {rpcUrls.map((row, idx) => (
                <div key={idx} className="flex gap-2">
                  <input
                    className="field w-[120px]"
                    value={row.chain}
                    placeholder="ethereum"
                    onChange={(e) =>
                      setRpcUrls((prev) =>
                        prev.map((r, i) => (i === idx ? { ...r, chain: e.target.value } : r)),
                      )
                    }
                  />
                  <input
                    className="field flex-1"
                    value={row.url}
                    placeholder="https://…"
                    onChange={(e) =>
                      setRpcUrls((prev) =>
                        prev.map((r, i) => (i === idx ? { ...r, url: e.target.value } : r)),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label="Remove RPC"
                    onClick={() => setRpcUrls((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rule" />

        <div className="flex flex-col gap-3">
          {addresses.length === 0 && (
            <div className="font-mono text-[11px] text-sillage-soft">
              No wallets yet. Add a public address to track balances.
            </div>
          )}
          {addresses.map((wallet, wIdx) => (
            <div
              key={wIdx}
              className="border border-sillage-line rounded-[10px] px-4 py-3.5 flex flex-col gap-3"
            >
              <div className="flex flex-wrap gap-2 items-end">
                <label className="flex flex-col gap-1.5 flex-1 min-w-[220px]">
                  <span className="lbl">Address</span>
                  <input
                    className="field"
                    value={wallet.address}
                    onChange={(e) =>
                      setAddresses((prev) =>
                        prev.map((a, i) => (i === wIdx ? { ...a, address: e.target.value } : a)),
                      )
                    }
                    placeholder="0x…"
                    autoComplete="off"
                  />
                </label>
                <label className="flex flex-col gap-1.5 w-[140px]">
                  <span className="lbl">Chain</span>
                  <input
                    className="field"
                    value={wallet.chain}
                    onChange={(e) =>
                      setAddresses((prev) =>
                        prev.map((a, i) => (i === wIdx ? { ...a, chain: e.target.value } : a)),
                      )
                    }
                    placeholder="ethereum"
                  />
                </label>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setAddresses((prev) => prev.filter((_, i) => i !== wIdx))}
                >
                  Remove
                </button>
              </div>

              <div className="flex items-center justify-between">
                <span className="lbl">Tokens</span>
                <button
                  type="button"
                  className="btn-ghost text-[10px]"
                  onClick={() =>
                    setAddresses((prev) =>
                      prev.map((a, i) =>
                        i === wIdx
                          ? {
                              ...a,
                              tokens: [...a.tokens, { address: '', symbol: '', decimals: 18 }],
                            }
                          : a,
                      ),
                    )
                  }
                >
                  + Token
                </button>
              </div>

              {wallet.tokens.map((token, tIdx) => (
                <div key={tIdx} className="flex flex-wrap gap-2 items-end">
                  <input
                    className="field flex-1 min-w-[180px]"
                    value={token.address}
                    placeholder="Token contract"
                    onChange={(e) =>
                      setAddresses((prev) =>
                        prev.map((a, i) =>
                          i === wIdx
                            ? {
                                ...a,
                                tokens: a.tokens.map((t, j) =>
                                  j === tIdx ? { ...t, address: e.target.value } : t,
                                ),
                              }
                            : a,
                        ),
                      )
                    }
                  />
                  <input
                    className="field w-[90px]"
                    value={token.symbol}
                    placeholder="USDC"
                    onChange={(e) =>
                      setAddresses((prev) =>
                        prev.map((a, i) =>
                          i === wIdx
                            ? {
                                ...a,
                                tokens: a.tokens.map((t, j) =>
                                  j === tIdx ? { ...t, symbol: e.target.value } : t,
                                ),
                              }
                            : a,
                        ),
                      )
                    }
                  />
                  <input
                    className="field w-[80px]"
                    type="number"
                    value={token.decimals}
                    onChange={(e) =>
                      setAddresses((prev) =>
                        prev.map((a, i) =>
                          i === wIdx
                            ? {
                                ...a,
                                tokens: a.tokens.map((t, j) =>
                                  j === tIdx
                                    ? { ...t, decimals: parseInt(e.target.value || '18', 10) }
                                    : t,
                                ),
                              }
                            : a,
                        ),
                      )
                    }
                  />
                  <button
                    type="button"
                    className="iconbtn"
                    aria-label="Remove token"
                    onClick={() =>
                      setAddresses((prev) =>
                        prev.map((a, i) =>
                          i === wIdx
                            ? { ...a, tokens: a.tokens.filter((_, j) => j !== tIdx) }
                            : a,
                        ),
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="font-mono text-[11px] text-sillage-soft">
          {status ? (
            <span className={status.kind === 'ok' ? 'text-sillage-green' : 'text-sillage-down'}>
              {status.text}
            </span>
          ) : (
            <span>Prefer read-only exchange keys. Restart is not required after save.</span>
          )}
        </div>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save configuration'}
        </button>
      </div>

    </form>
  )
}

function SecretInput({
  label,
  hint,
  isSet,
  value,
  onChange,
}: {
  label: string
  hint?: string | null
  isSet: boolean
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="lbl flex items-center justify-between gap-2">
        <span>{label}</span>
        {isSet && hint ? <span className="normal-case tracking-normal text-sillage-soft">{hint}</span> : null}
      </span>
      <input
        className="field"
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={isSet ? 'Leave blank to keep current' : 'Paste new value'}
        autoComplete="new-password"
      />
    </label>
  )
}
