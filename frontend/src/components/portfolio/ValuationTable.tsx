import { FormEvent, useState } from 'react'
import { format } from 'date-fns'
import { formatTokenPrice, formatUsdPrecise } from '../../utils/format'

export interface ValuationRow {
  id: number
  recordedAt: string
  valueAmount: number
  quantity: number | null
}

interface ValuationTableProps {
  symbol: string
  valuations: ValuationRow[]
  venue?: string | null
  showVenue?: boolean
  busy?: boolean
  onAdd?: (input: { recordedAt: string; valueAmount: number; quantity: number | null }) => Promise<void>
  onDelete?: (id: number) => Promise<void>
}

function impliedPrice(row: ValuationRow): number | null {
  if (row.quantity != null && row.quantity > 0) {
    return row.valueAmount / row.quantity
  }
  return null
}

/** Date-only inputs: use now when the day is today so later marks sort after earlier ones. */
function toRecordedAtIso(date: string): string {
  const now = new Date()
  const todayUtc = now.toISOString().slice(0, 10)
  if (date === todayUtc) return now.toISOString()
  return new Date(`${date}T12:00:00.000Z`).toISOString()
}

export default function ValuationTable({
  symbol,
  valuations,
  venue,
  showVenue = false,
  busy = false,
  onAdd,
  onDelete,
}: ValuationTableProps) {
  const [open, setOpen] = useState(false)
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [amount, setAmount] = useState('')
  const [quantity, setQuantity] = useState('')
  const [error, setError] = useState<string | null>(null)

  const rows = [...valuations].sort(
    (a, b) => new Date(b.recordedAt).getTime() - new Date(a.recordedAt).getTime(),
  )

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!onAdd) return
    setError(null)
    const valueAmount = Number(amount)
    if (!date || Number.isNaN(valueAmount)) {
      setError('Date and amount are required')
      return
    }
    const qty = quantity.trim() ? Number(quantity) : null
    if (qty != null && Number.isNaN(qty)) {
      setError('Quantity must be a number')
      return
    }
    await onAdd({
      recordedAt: toRecordedAtIso(date),
      valueAmount,
      quantity: qty,
    })
    setAmount('')
    setQuantity('')
    setOpen(false)
  }

  return (
    <div className="panel mt-4 sm:mt-5">
      <div className="flex justify-between items-baseline mb-1">
        <div className="lbl">Table 2 · Valuations</div>
        {onAdd && (
          <button
            type="button"
            className="font-mono text-[11px] tracking-wide uppercase border border-sillage-green text-sillage-green rounded-lg px-2.5 py-1 hover:bg-sillage-gsoft"
            onClick={() => setOpen((v) => !v)}
            disabled={busy}
          >
            {open ? 'Close' : '+ Add'}
          </button>
        )}
      </div>

      {open && onAdd && (
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end mb-3 mt-2">
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Date</span>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-transparent border border-sillage-line rounded-lg px-2 py-1.5 font-mono text-xs outline-none focus:border-sillage-green"
              disabled={busy}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Amount</span>
            <input
              type="number"
              step="any"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="bg-transparent border border-sillage-line rounded-lg px-2 py-1.5 font-mono text-xs outline-none focus:border-sillage-green w-28"
              disabled={busy}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Quantity</span>
            <input
              type="number"
              step="any"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="tokens"
              className="bg-transparent border border-sillage-line rounded-lg px-2 py-1.5 font-mono text-xs outline-none focus:border-sillage-green w-28"
              disabled={busy}
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="font-mono text-[11px] tracking-wide uppercase border border-sillage-green text-sillage-green rounded-lg px-3 py-1.5 hover:bg-sillage-gsoft disabled:opacity-50"
          >
            Save
          </button>
          {error && <span className="font-mono text-[11px] text-sillage-down">{error}</span>}
        </form>
      )}

      <div className="table-scroll">
        <div className="table-scroll-inner">
          <div className="trow text-sillage-soft border-t-0">
            <div className="w-24 lbl text-[9px]">Date</div>
            <div className="flex-1 lbl text-[9px]">Quantity</div>
            <div className="w-24 text-right lbl text-[9px]">Unit</div>
            <div className="w-24 text-right lbl text-[9px]">Value</div>
            {showVenue && <div className="w-24 text-right lbl text-[9px]">Venue</div>}
            {onDelete && <div className="w-16 text-right lbl text-[9px]"> </div>}
          </div>
          {rows.length === 0 ? (
            <div className="text-center py-8 text-sillage-soft text-sm">No valuations yet</div>
          ) : (
            rows.map((row) => {
              const unit = impliedPrice(row)
              return (
                <div key={row.id} className="trow items-center">
                  <div className="w-24 font-mono text-[11px] text-sillage-soft">
                    {format(new Date(row.recordedAt), 'MMM dd, yy')}
                  </div>
                  <div className="flex-1 font-mono tabular-nums text-xs">
                    {row.quantity != null
                      ? `${row.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${symbol}`
                      : '—'}
                  </div>
                  <div className="w-24 text-right font-mono tabular-nums text-xs">
                    {unit != null ? formatTokenPrice(unit) : '—'}
                  </div>
                  <div className="w-24 text-right font-mono tabular-nums text-xs">
                    {formatUsdPrecise(row.valueAmount)}
                  </div>
                  {showVenue && (
                    <div className="w-24 text-right font-mono text-[11px] text-sillage-soft">
                      {venue || '—'}
                    </div>
                  )}
                  {onDelete && (
                    <div className="w-16 text-right">
                      <button
                        type="button"
                        className="font-mono text-[9px] text-sillage-down hover:opacity-80"
                        onClick={() => onDelete(row.id)}
                        disabled={busy}
                      >
                        delete
                      </button>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
