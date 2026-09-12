import { FormEvent, useMemo, useState, type ChangeEvent } from 'react'
import { useMutation, useQuery } from '@apollo/client'
import { GET_PORTFOLIO } from '../../graphql/queries'
import {
  CREATE_MANUAL_POSITION,
  DELETE_MANUAL_POSITION,
  UPDATE_MANUAL_POSITION,
} from '../../graphql/mutations'
import { formatUsdPrecise } from '../../utils/format'

interface ManualRow {
  id: number
  symbol: string
  exchange: string | null
  displayName: string | null
  externalUrl: string | null
  source: string
  value: number
  quantity: number
}

const emptyForm = {
  displayName: '',
  symbol: '',
  exchange: '',
  externalUrl: '',
  initialValue: '',
  initialQuantity: '',
}

export default function ManualPositionsSettings() {
  const { data, loading, refetch } = useQuery(GET_PORTFOLIO)
  const [createPosition] = useMutation(CREATE_MANUAL_POSITION)
  const [updatePosition] = useMutation(UPDATE_MANUAL_POSITION)
  const [deletePosition] = useMutation(DELETE_MANUAL_POSITION)

  const [form, setForm] = useState(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const rows: ManualRow[] = useMemo(() => {
    const list = (data?.portfolio?.positions ?? []) as ManualRow[]
    return list
      .filter((p) => p.source === 'manual')
      .sort((a, b) => a.symbol.localeCompare(b.symbol))
  }, [data])

  const onField =
    (key: keyof typeof emptyForm) =>
    (e: ChangeEvent<HTMLInputElement>) => {
      setForm((prev) => ({ ...prev, [key]: e.target.value }))
    }

  const resetForm = () => {
    setForm(emptyForm)
    setEditingId(null)
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!form.displayName.trim() || !form.symbol.trim() || !form.exchange.trim()) {
      setError('Name, symbol, and venue are required')
      return
    }
    setBusy(true)
    try {
      if (editingId != null) {
        await updatePosition({
          variables: {
            id: editingId,
            displayName: form.displayName.trim(),
            symbol: form.symbol.trim(),
            exchange: form.exchange.trim(),
            externalUrl: form.externalUrl.trim() || null,
          },
        })
      } else {
        const initialValue = form.initialValue.trim()
          ? Number(form.initialValue)
          : null
        const initialQuantity = form.initialQuantity.trim()
          ? Number(form.initialQuantity)
          : null
        if (initialValue != null && Number.isNaN(initialValue)) {
          setError('Initial value must be a number')
          setBusy(false)
          return
        }
        if (initialQuantity != null && Number.isNaN(initialQuantity)) {
          setError('Initial quantity must be a number')
          setBusy(false)
          return
        }
        await createPosition({
          variables: {
            displayName: form.displayName.trim(),
            symbol: form.symbol.trim(),
            exchange: form.exchange.trim(),
            externalUrl: form.externalUrl.trim() || null,
            initialValue,
            initialQuantity,
          },
        })
      }
      resetForm()
      await refetch()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save position')
    } finally {
      setBusy(false)
    }
  }

  const onEdit = (row: ManualRow) => {
    setEditingId(row.id)
    setForm({
      displayName: row.displayName || '',
      symbol: row.symbol,
      exchange: row.exchange || '',
      externalUrl: row.externalUrl || '',
      initialValue: '',
      initialQuantity: '',
    })
  }

  const onDelete = async (row: ManualRow) => {
    const label = row.displayName || row.symbol
    if (!window.confirm(`Delete manual position “${label}”? Valuation history will be removed.`)) {
      return
    }
    setError(null)
    setBusy(true)
    try {
      await deletePosition({ variables: { id: row.id } })
      if (editingId === row.id) resetForm()
      await refetch()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete position')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading manual positions…</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-end mb-[18px]">
        <div>
          <div className="lbl">Manual positions</div>
          <div className="font-serif text-[22px] leading-none mt-[7px]">Off-API holdings</div>
        </div>
        <div className="cap max-w-sm text-right">
          Declare cash parked on tools without an API. Add valuation snapshots from the position
          page.
        </div>
      </div>

      {error && <div className="panel mb-4 text-sillage-down font-mono text-xs">{error}</div>}

      <div className="flex gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel w-full lg:w-[320px] flex-shrink-0">
          <div className="lbl mb-3">{editingId != null ? 'Edit position' : 'New position'}</div>
          <form onSubmit={onSubmit} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Name</span>
              <input
                type="text"
                value={form.displayName}
                onChange={onField('displayName')}
                placeholder="e.g. EstateGuru"
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                disabled={busy}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Symbol</span>
              <input
                type="text"
                value={form.symbol}
                onChange={onField('symbol')}
                placeholder="e.g. ETH or ESTATE"
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                disabled={busy}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Venue</span>
              <input
                type="text"
                value={form.exchange}
                onChange={onField('exchange')}
                placeholder="Platform name"
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                disabled={busy}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="lbl text-[9px]">Link</span>
              <input
                type="url"
                value={form.externalUrl}
                onChange={onField('externalUrl')}
                placeholder="https://…"
                className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                disabled={busy}
              />
            </label>
            {editingId == null && (
              <>
                <label className="flex flex-col gap-1.5">
                  <span className="lbl text-[9px]">Initial value</span>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={form.initialValue}
                    onChange={onField('initialValue')}
                    placeholder="Optional"
                    className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                    disabled={busy}
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="lbl text-[9px]">Initial quantity</span>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={form.initialQuantity}
                    onChange={onField('initialQuantity')}
                    placeholder="Optional tokens"
                    className="bg-transparent border border-sillage-line rounded-lg px-3 py-2 font-mono text-xs text-sillage-ink outline-none focus:border-sillage-green"
                    disabled={busy}
                  />
                </label>
              </>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy}
                className="flex-1 font-mono text-[11px] tracking-wide uppercase border border-sillage-green text-sillage-green rounded-lg px-3 py-2 hover:bg-sillage-gsoft transition-colors disabled:opacity-50"
              >
                {editingId != null ? 'Save changes' : 'Create position'}
              </button>
              {editingId != null && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={resetForm}
                  className="font-mono text-[11px] tracking-wide uppercase border border-sillage-line text-sillage-soft rounded-lg px-3 py-2 hover:text-sillage-ink disabled:opacity-50"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>

        <div className="panel flex-1 min-w-0">
          <div className="flex justify-between items-baseline mb-1">
            <div className="lbl">Declared positions</div>
            <div className="cap">{rows.length} open</div>
          </div>
          {rows.length === 0 ? (
            <div className="text-center py-10 text-sillage-soft text-sm">
              No manual positions yet.
            </div>
          ) : (
            <>
              <div className="trow text-sillage-soft border-t-0">
                <div className="w-28 lbl text-[9px]">Name</div>
                <div className="w-20 lbl text-[9px]">Symbol</div>
                <div className="w-28 lbl text-[9px]">Venue</div>
                <div className="flex-1 text-right lbl text-[9px]">Value</div>
                <div className="w-24 text-right lbl text-[9px]"> </div>
              </div>
              {rows.map((row) => (
                <div key={row.id} className="trow items-center">
                  <div className="w-28 font-mono text-xs truncate">
                    {row.displayName || row.symbol}
                  </div>
                  <div className="w-20 tk">{row.symbol}</div>
                  <div className="w-28">
                    <span className="chip">{row.exchange || 'manual'}</span>
                  </div>
                  <div className="flex-1 text-right font-mono tabular-nums text-xs">
                    {formatUsdPrecise(row.value)}
                  </div>
                  <div className="w-24 text-right flex justify-end gap-2">
                    <button
                      type="button"
                      className="font-mono text-[9px] text-sillage-soft hover:text-sillage-ink"
                      onClick={() => onEdit(row)}
                      disabled={busy}
                    >
                      edit
                    </button>
                    <button
                      type="button"
                      className="font-mono text-[9px] text-sillage-down hover:opacity-80"
                      onClick={() => onDelete(row)}
                      disabled={busy}
                    >
                      delete
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
