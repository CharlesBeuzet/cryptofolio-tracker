import { FormEvent, useState } from 'react'

interface OnchainBuyFormProps {
  symbol: string
  unpriced: number
  busy?: boolean
  onAdd: (input: { quantity: number; price: number; executedAt: string }) => Promise<void>
}

/** Date-only inputs: use now when the day is today so the order sorts after earlier ones. */
function toExecutedAtIso(date: string): string {
  const now = new Date()
  const todayUtc = now.toISOString().slice(0, 10)
  if (date === todayUtc) return now.toISOString()
  return new Date(`${date}T12:00:00.000Z`).toISOString()
}

export default function OnchainBuyForm({
  symbol,
  unpriced,
  busy = false,
  onAdd,
}: OnchainBuyFormProps) {
  const [open, setOpen] = useState(false)
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState<string | null>(null)
  const canAdd = unpriced > 1e-8

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const qty = Number(quantity)
    const unit = Number(price)
    if (!date || !Number.isFinite(qty) || qty <= 0 || !Number.isFinite(unit) || unit <= 0) {
      setError('Date, quantity, and buy price are required.')
      return
    }
    if (qty - unpriced > 1e-8) {
      setError(`Quantity cannot exceed the unpriced holding (${unpriced}).`)
      return
    }
    try {
      await onAdd({
        quantity: qty,
        price: unit,
        executedAt: toExecutedAtIso(date),
      })
      setQuantity('')
      setPrice('')
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the buy.')
    }
  }

  return (
    <div className="mb-3">
      <div className="flex justify-between items-baseline gap-3">
        <p className="cap">
          {canAdd
            ? `${unpriced.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${symbol} still without a buy price.`
            : 'Every token in this holding has a buy price.'}
        </p>
        {canAdd && (
          <button
            type="button"
            className="font-mono text-[11px] tracking-wide uppercase border border-sillage-green text-sillage-green rounded-lg px-2.5 py-1 hover:bg-sillage-gsoft"
            onClick={() => {
              setError(null)
              setOpen((value) => !value)
            }}
            disabled={busy}
          >
            {open ? 'Close' : '+ Add buy'}
          </button>
        )}
      </div>
      {open && canAdd && (
        <form onSubmit={submit} className="flex flex-wrap gap-2 items-end mt-2">
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Date</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="bg-transparent border border-sillage-line rounded-lg px-2 py-1.5 font-mono text-xs outline-none focus:border-sillage-green"
              disabled={busy}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Quantity</span>
            <input
              type="number"
              step="any"
              min="0"
              max={unpriced}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="tokens"
              className="bg-transparent border border-sillage-line rounded-lg px-2 py-1.5 font-mono text-xs outline-none focus:border-sillage-green w-28"
              disabled={busy}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="lbl text-[9px]">Buy price</span>
            <input
              type="number"
              step="any"
              min="0"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              placeholder="0.00"
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
    </div>
  )
}
