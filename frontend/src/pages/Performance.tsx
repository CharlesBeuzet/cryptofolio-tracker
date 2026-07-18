import { useMemo } from 'react'
import { useQuery } from '@apollo/client'
import { Link } from 'react-router-dom'
import { GET_PORTFOLIO } from '../graphql/queries'
import { assetColor, formatPct, formatUsd, formatUsdPrecise, pnlColorClass } from '../utils/format'

interface Tag {
  id: number
  name: string
  color: string | null
  description: string | null
}

interface Position {
  id: number
  symbol: string
  value: number
  pnl: number | null
  pnlPercent: number | null
  exchange: string | null
  avgEntryPrice: number
  quantity: number
  tag: Tag | null
}

interface ThesisGroup {
  key: string
  name: string
  color: string
  note: string
  positions: Position[]
  totalValue: number
  totalCost: number
  pnlPct: number
  sharePct: number
}

const VENUE_NOTES: Record<string, string> = {
  binance: 'Centralized exchange positions — liquid, actively rebalanced.',
  coinbase: 'Regulated venue holdings — lower counterparty risk profile.',
  wallet: 'Self-custody assets — full control, no exchange dependency.',
}

function buildGroups(
  positions: Position[],
  totalBook: number,
  keyFn: (p: Position) => string,
  nameFn: (key: string, sample: Position | undefined) => string,
  colorFn: (key: string, index: number, sample: Position | undefined) => string,
  noteFn: (key: string, sample: Position | undefined) => string,
): ThesisGroup[] {
  const groups: Record<string, Position[]> = {}
  positions.forEach((p) => {
    const key = keyFn(p)
    if (!groups[key]) groups[key] = []
    groups[key].push(p)
  })

  return Object.entries(groups)
    .map(([key, list], gi) => {
      const totalValue = list.reduce((s, p) => s + p.value, 0)
      const totalCost = list.reduce((s, p) => s + p.avgEntryPrice * p.quantity, 0)
      const pnlPct = totalCost > 0 ? ((totalValue - totalCost) / totalCost) * 100 : 0
      const sample = list[0]
      return {
        key,
        name: nameFn(key, sample),
        color: colorFn(key, gi, sample),
        note: noteFn(key, sample),
        positions: [...list].sort((a, b) => b.value - a.value),
        totalValue,
        totalCost,
        pnlPct,
        sharePct: totalBook > 0 ? (totalValue / totalBook) * 100 : 0,
      }
    })
    .sort((a, b) => b.totalValue - a.totalValue)
}

function ThesisPanels({ theses }: { theses: ThesisGroup[] }) {
  if (theses.length === 0) {
    return <div className="panel text-center py-12 text-sillage-soft text-sm">No positions to analyze yet.</div>
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {theses.map((t) => (
        <div key={t.key} className="panel">
          <div className="flex justify-between items-start">
            <div className="flex items-center gap-2.5">
              <span className="sw w-[11px] h-[11px]" style={{ background: t.color }} />
              <div className="font-serif text-xl">{t.name}</div>
              <span className="chip">
                {t.positions.length} position{t.positions.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="text-right">
              <div className="font-mono tabular-nums font-semibold text-[17px]">
                {formatUsd(t.totalValue)}
              </div>
              <div className={`font-mono text-[11px] ${pnlColorClass(t.pnlPct)}`}>
                {formatPct(t.pnlPct)}
              </div>
            </div>
          </div>

          <div className="wbar mt-4">
            <div className="wfill" style={{ width: `${t.sharePct}%`, background: t.color }} />
          </div>
          <div className="font-mono text-sillage-soft text-[9px] mt-1.5 tracking-widest">
            {t.sharePct.toFixed(1)}% OF BOOK
          </div>

          <div className="mt-3.5 flex flex-col">
            {t.positions.map((p) => (
              <Link
                key={p.id}
                to={`/position/${p.id}`}
                className="trow cursor-pointer no-underline text-inherit hover:bg-sillage-gsoft transition-colors"
              >
                <span className="tk flex-1">{p.symbol}</span>
                <span className="chip mr-2">{p.exchange || 'other'}</span>
                {p.tag && <span className="chip mr-2">{p.tag.name}</span>}
                <span className="font-mono tabular-nums text-xs text-sillage-soft">
                  {formatUsdPrecise(p.value)}
                </span>
                <span
                  className={`font-mono text-xs w-[60px] text-right tabular-nums ${pnlColorClass(p.pnlPercent || 0)}`}
                >
                  {formatPct(p.pnlPercent || 0)}
                </span>
              </Link>
            ))}
          </div>

          <div className="cap mt-3.5 leading-normal">{t.note}</div>
        </div>
      ))}
    </div>
  )
}

export default function Performance() {
  const { data, loading } = useQuery(GET_PORTFOLIO)

  const positions: Position[] = data?.portfolio?.positions || []
  const totalBook = positions.reduce((s, p) => s + p.value, 0)

  const venueTheses = useMemo(
    () =>
      buildGroups(
        positions,
        totalBook,
        (p) => (p.exchange || 'other').toLowerCase(),
        (key) => key.charAt(0).toUpperCase() + key.slice(1),
        (_key, gi) => assetColor(gi),
        (key) =>
          VENUE_NOTES[key] || 'Positions held across this venue — track allocation and P&L here.',
      ),
    [positions, totalBook],
  )

  const tagTheses = useMemo(
    () =>
      buildGroups(
        positions,
        totalBook,
        (p) => (p.tag ? `tag:${p.tag.id}` : 'untagged'),
        (key, sample) => (key === 'untagged' ? 'Untagged' : sample?.tag?.name || 'Tag'),
        (key, gi, sample) =>
          key === 'untagged' ? 'var(--soft)' : sample?.tag?.color || assetColor(gi),
        (key, sample) =>
          key === 'untagged'
            ? 'Positions without a conviction tag — assign one in Settings.'
            : sample?.tag?.description ||
              'Tagged positions tracked as a separate thesis across venues.',
      ),
    [positions, totalBook],
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading performance data…</div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-end mb-[18px]">
        <div>
          <div className="lbl">§4 · Theses</div>
          <div className="font-serif text-[26px] leading-none mt-[7px]">Performance by conviction</div>
        </div>
        <div className="cap max-w-sm text-right">
          Venue books stay intact — conviction tags add a second lens from Settings.
        </div>
      </div>

      <div className="lbl mb-3">By venue</div>
      <ThesisPanels theses={venueTheses} />

      <div className="flex justify-between items-end mt-10 mb-3">
        <div className="lbl">By tag</div>
        <Link to="/settings" className="cap no-underline hover:text-sillage-ink">
          Manage tags in Settings ↗
        </Link>
      </div>
      <ThesisPanels theses={tagTheses} />
    </div>
  )
}
