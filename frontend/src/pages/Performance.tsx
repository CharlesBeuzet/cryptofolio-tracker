import { useMemo } from 'react'
import { useQuery } from '@apollo/client'
import { Link } from 'react-router-dom'
import { GET_PORTFOLIO } from '../graphql/queries'
import { assetColor, formatPct, formatUsd, formatUsdPrecise, pnlColorClass } from '../utils/format'

interface Position {
  id: number
  symbol: string
  value: number
  pnl: number | null
  pnlPercent: number | null
  exchange: string | null
  avgEntryPrice: number
  quantity: number
}

interface ThesisGroup {
  name: string
  color: string
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

export default function Performance() {
  const { data, loading } = useQuery(GET_PORTFOLIO)

  const positions = data?.portfolio?.positions || []
  const totalBook = positions.reduce((s: number, p: { value: number }) => s + p.value, 0)

  const theses: ThesisGroup[] = useMemo(() => {
    const groups: Record<string, typeof positions> = {}
    positions.forEach((p: (typeof positions)[number]) => {
      const key = (p.exchange || 'other').toLowerCase()
      if (!groups[key]) groups[key] = []
      groups[key].push(p)
    })

    return Object.entries(groups)
      .map(([name, list], gi) => {
        const totalValue = list.reduce((s: number, p: Position) => s + p.value, 0)
        const totalCost = list.reduce((s: number, p: Position) => s + p.avgEntryPrice * p.quantity, 0)
        const pnlPct = totalCost > 0 ? ((totalValue - totalCost) / totalCost) * 100 : 0
        return {
          name: name.charAt(0).toUpperCase() + name.slice(1),
          color: assetColor(gi),
          positions: [...list].sort((a, b) => b.value - a.value),
          totalValue,
          totalCost,
          pnlPct,
          sharePct: totalBook > 0 ? (totalValue / totalBook) * 100 : 0,
        }
      })
      .sort((a, b) => b.totalValue - a.totalValue)
  }, [positions, totalBook])

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
        <div className="cap">Grouped by venue — tag wallets and positions to track each thesis separately.</div>
      </div>

      {theses.length === 0 ? (
        <div className="panel text-center py-12 text-sillage-soft text-sm">No positions to analyze yet.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {theses.map((t) => (
            <div key={t.name} className="panel">
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

              <div className="cap mt-3.5 leading-normal">
                {VENUE_NOTES[t.name.toLowerCase()] ||
                  'Positions held across this venue — track allocation and P&L here.'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
