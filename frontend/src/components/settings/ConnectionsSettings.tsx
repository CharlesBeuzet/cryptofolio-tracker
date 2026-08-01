import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@apollo/client'
import { GET_APP_CONFIG, UPDATE_APP_CONFIG } from '../../graphql/queries'

type SecretField = { isSet: boolean; hint?: string | null }

type AvailableConnector = {
  name: string
  label: string
  supportsPassphrase: boolean
  supportsHostname: boolean
  requiredSecrets: string[]
}

type ExchangeConfig = {
  name: string
  label: string
  configured: boolean
  supportsPassphrase: boolean
  supportsHostname: boolean
  sandbox?: boolean | null
  hostname?: string | null
  apiKey: SecretField
  apiSecret: SecretField
  passphrase: SecretField
}

type WalletAddress = { address: string; chain: string }
type RpcUrl = { chain: string; url: string }

type ExchangeDraft = {
  name: string
  label: string
  supportsPassphrase: boolean
  supportsHostname: boolean
  apiKey: string
  apiSecret: string
  passphrase: string
  hostname: string
  sandbox: boolean
  /** True when freshly added and not yet persisted */
  isNew?: boolean
}

type StatusMsg = { kind: 'ok' | 'err'; text: string } | null

export default function ConnectionsSettings() {
  const { data, loading, error, refetch } = useQuery(GET_APP_CONFIG)
  const [updateConfig, { loading: saving }] = useMutation(UPDATE_APP_CONFIG)

  const [exchanges, setExchanges] = useState<ExchangeDraft[]>([])
  const [serverExchanges, setServerExchanges] = useState<ExchangeConfig[]>([])
  const [available, setAvailable] = useState<AvailableConnector[]>([])
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [adding, setAdding] = useState(false)
  const [pickName, setPickName] = useState('')

  const [defaultRpc, setDefaultRpc] = useState('')
  const [rpcUrls, setRpcUrls] = useState<RpcUrl[]>([])
  const [addresses, setAddresses] = useState<WalletAddress[]>([])
  const [walletsOpen, setWalletsOpen] = useState(false)
  const [status, setStatus] = useState<StatusMsg>(null)
  const [metaExists, setMetaExists] = useState(false)

  useEffect(() => {
    const cfg = data?.appConfig
    if (!cfg) return

    setMetaExists(Boolean(cfg.exists))
    setAvailable(cfg.availableConnectors || [])
    setServerExchanges(cfg.exchanges || [])
    setExchanges(
      (cfg.exchanges || []).map((ex: ExchangeConfig) => ({
        name: ex.name,
        label: ex.label || ex.name,
        supportsPassphrase: ex.supportsPassphrase,
        supportsHostname: ex.supportsHostname,
        apiKey: '',
        apiSecret: '',
        passphrase: '',
        hostname: ex.hostname || '',
        sandbox: Boolean(ex.sandbox),
        isNew: false,
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
      })),
    )
    // Collapse all after reload except brand-new drafts handled locally
    setExpanded({})
    setAdding(false)
    setPickName('')
  }, [data])

  const addable = useMemo(() => {
    const active = new Set(exchanges.map((ex) => ex.name))
    return available.filter((item) => !active.has(item.name))
  }, [available, exchanges])

  const walletsActive = Boolean(
    defaultRpc.trim() || rpcUrls.length > 0 || addresses.some((a) => a.address.trim()),
  )

  const updateExchange = (name: string, patch: Partial<ExchangeDraft>) => {
    setExchanges((prev) => prev.map((ex) => (ex.name === name ? { ...ex, ...patch } : ex)))
  }

  const toggleExpanded = (name: string) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }))
  }

  const startAdd = () => {
    setAdding(true)
    setPickName(addable[0]?.name || '')
  }

  const confirmAdd = () => {
    const catalog = available.find((item) => item.name === pickName)
    if (!catalog) return
    if (exchanges.some((ex) => ex.name === catalog.name)) return

    const draft: ExchangeDraft = {
      name: catalog.name,
      label: catalog.label,
      supportsPassphrase: catalog.supportsPassphrase,
      supportsHostname: catalog.supportsHostname,
      apiKey: '',
      apiSecret: '',
      passphrase: '',
      hostname: '',
      sandbox: false,
      isNew: true,
    }
    setExchanges((prev) => [...prev, draft])
    setExpanded((prev) => ({ ...prev, [catalog.name]: true }))
    setAdding(false)
    setPickName('')
    setStatus(null)
  }

  const removeExchange = (name: string) => {
    setExchanges((prev) => prev.filter((ex) => ex.name !== name))
    setExpanded((prev) => {
      const next = { ...prev }
      delete next[name]
      return next
    })
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setStatus(null)

    // Validate new connectors have required secrets before save
    for (const ex of exchanges) {
      if (!ex.isNew) continue
      const catalog = available.find((item) => item.name === ex.name)
      const required = catalog?.requiredSecrets || ['api_key', 'api_secret']
      const values: Record<string, string> = {
        api_key: ex.apiKey,
        api_secret: ex.apiSecret,
        passphrase: ex.passphrase,
      }
      const missing = required.filter((key) => !values[key]?.trim())
      if (missing.length) {
        setStatus({
          kind: 'err',
          text: `${ex.label}: fill ${missing.join(', ')} before saving.`,
        })
        setExpanded((prev) => ({ ...prev, [ex.name]: true }))
        return
      }
    }

    try {
      const result = await updateConfig({
        variables: {
          replaceExchanges: true,
          exchanges: exchanges.map((ex) => ({
            name: ex.name,
            apiKey: ex.apiKey.trim() || null,
            apiSecret: ex.apiSecret.trim() || null,
            passphrase: ex.passphrase.trim() || null,
            hostname: ex.supportsHostname ? ex.hostname.trim() : null,
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
              Active connectors are listed below. Open a card to edit credentials, or add one from
              the connectors available in this project.
            </p>
          </div>
          <span className="chip">{metaExists ? 'Configured' : 'Empty'}</span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="lbl">Active connectors</div>
          {addable.length > 0 && !adding && (
            <button type="button" className="btn-ghost" onClick={startAdd}>
              + Add connector
            </button>
          )}
        </div>

        {exchanges.length === 0 && !adding && (
          <div className="panel text-sillage-soft font-mono text-sm">
            No connectors declared yet. Add Binance or OKX to get started.
          </div>
        )}

        {exchanges.map((ex) => {
          const server = serverExchanges.find((s) => s.name === ex.name)
          const isOpen = Boolean(expanded[ex.name])
          return (
            <div key={ex.name} className="panel !py-0 !px-0 overflow-hidden">
              <button
                type="button"
                className="w-full flex items-center justify-between gap-3 px-6 py-4 text-left cursor-pointer bg-transparent border-0 text-inherit"
                onClick={() => toggleExpanded(ex.name)}
                aria-expanded={isOpen}
              >
                <div className="font-serif text-[20px] leading-none">{ex.label}</div>
                <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-wide text-sillage-green">
                  <span
                    className="w-[7px] h-[7px] rounded-full bg-sillage-green inline-block"
                    aria-hidden
                  />
                  Active
                  <span className="text-sillage-soft ml-1">{isOpen ? '▾' : '▸'}</span>
                </span>
              </button>

              {isOpen && (
                <div className="px-6 pb-5 pt-1 flex flex-col gap-3.5 border-t border-sillage-line">
                  {ex.isNew && (
                    <p className="cap">
                      New connector — fill the required fields, then save to declare it.
                    </p>
                  )}

                  <SecretInput
                    label="API key"
                    hint={server?.apiKey.hint}
                    isSet={Boolean(server?.apiKey.isSet)}
                    value={ex.apiKey}
                    onChange={(value) => updateExchange(ex.name, { apiKey: value })}
                    required={ex.isNew}
                  />
                  <SecretInput
                    label="API secret"
                    hint={server?.apiSecret.hint}
                    isSet={Boolean(server?.apiSecret.isSet)}
                    value={ex.apiSecret}
                    onChange={(value) => updateExchange(ex.name, { apiSecret: value })}
                    required={ex.isNew}
                  />
                  {ex.supportsPassphrase && (
                    <SecretInput
                      label="Passphrase"
                      hint={server?.passphrase.hint}
                      isSet={Boolean(server?.passphrase.isSet)}
                      value={ex.passphrase}
                      onChange={(value) => updateExchange(ex.name, { passphrase: value })}
                      required={ex.isNew}
                    />
                  )}

                  {ex.supportsHostname && (
                    <label className="flex flex-col gap-1.5">
                      <span className="lbl">Hostname (optional)</span>
                      <input
                        className="field"
                        value={ex.hostname}
                        onChange={(e) => updateExchange(ex.name, { hostname: e.target.value })}
                        placeholder="openapi.okx.com"
                        autoComplete="off"
                      />
                    </label>
                  )}

                  <label className="flex items-center gap-2.5 font-mono text-[11px] text-sillage-soft cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={ex.sandbox}
                      onChange={(e) => updateExchange(ex.name, { sandbox: e.target.checked })}
                      className="accent-[var(--green)]"
                    />
                    Sandbox / testnet
                  </label>

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      className="btn-ghost text-sillage-down"
                      onClick={() => removeExchange(ex.name)}
                    >
                      Remove connector
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}

        {adding && (
          <div className="panel flex flex-col gap-3.5">
            <div>
              <div className="lbl">New connector</div>
              <div className="font-serif text-[20px] leading-none mt-1.5">Choose a type</div>
            </div>
            <label className="flex flex-col gap-1.5">
              <span className="lbl">Available connectors</span>
              <select
                className="field"
                value={pickName}
                onChange={(e) => setPickName(e.target.value)}
              >
                {addable.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap gap-2 justify-end">
              <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={confirmAdd}
                disabled={!pickName}
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {addable.length === 0 && exchanges.length > 0 && (
          <div className="font-mono text-[11px] text-sillage-soft">
            All project connectors are already declared.
          </div>
        )}
      </div>

      <div className="panel !py-0 !px-0 overflow-hidden">
        <button
          type="button"
          className="w-full flex items-center justify-between gap-3 px-6 py-4 text-left cursor-pointer bg-transparent border-0 text-inherit"
          onClick={() => setWalletsOpen((v) => !v)}
          aria-expanded={walletsOpen}
        >
          <div className="font-serif text-[20px] leading-none">Hot wallets</div>
          {walletsActive ? (
            <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-wide text-sillage-green">
              <span className="w-[7px] h-[7px] rounded-full bg-sillage-green inline-block" aria-hidden />
              Active
              <span className="text-sillage-soft ml-1">{walletsOpen ? '▾' : '▸'}</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-wide text-sillage-soft">
              Inactive
              <span className="ml-1">{walletsOpen ? '▾' : '▸'}</span>
            </span>
          )}
        </button>

        {walletsOpen && (
          <div className="px-6 pb-5 pt-1 flex flex-col gap-4 border-t border-sillage-line">
            <p className="cap">Public addresses only — never paste a private key.</p>

            <div className="flex justify-end">
              <button
                type="button"
                className="btn-ghost"
                onClick={() =>
                  setAddresses((prev) => [...prev, { address: '', chain: 'ethereum' }])
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
                    <div className="font-mono text-[11px] text-sillage-soft">
                      None — using default RPC.
                    </div>
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
                            prev.map((a, i) =>
                              i === wIdx ? { ...a, address: e.target.value } : a,
                            ),
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
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="font-mono text-[11px] text-sillage-soft">
          {status ? (
            <span className={status.kind === 'ok' ? 'text-sillage-green' : 'text-sillage-down'}>
              {status.text}
            </span>
          ) : (
            <span>Prefer read-only exchange keys. Leave secret fields blank to keep current values.</span>
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
  required,
}: {
  label: string
  hint?: string | null
  isSet: boolean
  value: string
  onChange: (value: string) => void
  required?: boolean
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="lbl flex items-center justify-between gap-2">
        <span>
          {label}
          {required ? ' *' : ''}
        </span>
        {isSet && hint ? (
          <span className="normal-case tracking-normal text-sillage-soft">{hint}</span>
        ) : null}
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
