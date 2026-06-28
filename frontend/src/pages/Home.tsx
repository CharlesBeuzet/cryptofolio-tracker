import { useQuery } from '@apollo/client'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GET_PORTFOLIO, GET_PORTFOLIO_HISTORY, GET_FIAT_DEPOSITS_SUMMARY } from '../graphql/queries'
import PortfolioValueChart from '../components/charts/PortfolioValueChart'
import AllocationDonut from '../components/charts/AllocationDonut'
import RangeSegment, { rangeLabel, rangeToDays, type RangeKey } from '../components/common/RangeSegment'
import { assetColor, formatPct, formatUsd, formatUsdPrecise, pnlColorClass } from '../utils/format'

export default function Home() {
  const [range, setRange] = useState<RangeKey>('90d')

  const { data: portfolioData, loading: portfolioLoading } = useQuery(GET_PORTFOLIO)
  const { data: historyData, loading: historyLoading } = useQuery(GET_PORTFOLIO_HISTORY, {
    variables: { days: rangeToDays(range) },
  })
  const { data: fiatSummaryData } = useQuery(GET_FIAT_DEPOSITS_SUMMARY)

  if (portfolioLoading || historyLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading portfolio data…</div>
      </div>
    )
  }

  const portfolio = portfolioData?.portfolio
  const history = historyData?.portfolioHistory || []
  const positions = portfolio?.positions || []
  const totalValue = portfolio?.totalValue || 0
  const sorted = [...positions].sort((a, b) => b.value - a.value)
  const totalBook = sorted.reduce((s, p) => s + p.value, 0)

  const fiatTotal = (fiatSummaryData?.fiatDepositsSummary?.totalsByCurrency || []).reduce(
    (s: number, r: { totalAmount: number }) => s + r.totalAmount,
    0,
  )
  const pnl = totalValue - fiatTotal

  return (
    <div>
      <div className="flex justify-between items-end mb-[18px]">
        <div>
          <div className="lbl">§1 · Overview</div>
          <div className="font-serif text-[26px] leading-none mt-[7px]">Consolidated positions</div>
        </div>
        <RangeSegment value={range} onChange={setRange} />
      </div>

      <div className="panel p-0 overflow-hidden relative">
        <div className="absolute left-6 top-5 z-10 pointer-events-none">
          <div className="lbl">Net asset value · {rangeLabel(range)}</div>
          <div className="font-serif text-[46px] leading-none mt-1.5">{formatUsd(totalValue)}</div>
          <div className="font-mono text-xs mt-[7px] text-sillage-soft">
            NAV = deposits + P&amp;L ⟶{' '}
            <span className="tabular-nums">{formatUsd(totalValue)}</span> ={' '}
            <span className="tabular-nums">{formatUsd(fiatTotal)}</span> +{' '}
            <span className={`tabular-nums ${pnlColorClass(pnl)}`}>{formatUsd(pnl)}</span>
          </div>
        </div>
        <PortfolioValueChart data={history} height={250} />
      </div>

      <div className="flex gap-5 mt-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          <div className="flex justify-between items-baseline mb-1">
            <div className="lbl">Table 1 · Positions by asset</div>
            <div className="cap">click a row to inspect ↗</div>
          </div>

          {sorted.length === 0 ? (
            <div className="text-center py-8 text-sillage-soft text-sm">No positions found</div>
          ) : (
            sorted.map((position, i) => {
              const share = totalBook > 0 ? (position.value / totalBook) * 100 : 0
              const pnlVal = position.pnl || 0
              const exchange = position.exchange || '—'

              return (
                <Link key={position.id} to={`/position/${position.id}`} className="hrow no-underline text-inherit">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="sw" style={{ background: assetColor(i) }} />
                      <span className="tk">{position.symbol}</span>
                      <span className="chip">{exchange}</span>
                    </div>
                    <div className="text-sillage-soft text-[11px] mt-[3px] ml-[18px] font-mono">
                      {position.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                    </div>
                  </div>
                  <div className="w-24 text-right font-mono tabular-nums text-[13px]">
                    {formatUsdPrecise(position.value)}
                  </div>
                  <div className="w-20">
                    <div className="wbar">
                      <div className="wfill" style={{ width: `${share}%` }} />
                    </div>
                    <div className="text-sillage-soft font-mono text-[9px] mt-[3px] text-right tabular-nums">
                      {share.toFixed(1)}%
                    </div>
                  </div>
                  <div className={`w-[74px] text-right font-mono text-xs tabular-nums ${pnlColorClass(pnlVal)}`}>
                    {formatPct(position.pnlPercent || 0)}
                  </div>
                </Link>
              )
            })
          )}

          <div className="rule mt-3" />
          <div className="font-mono text-sillage-soft text-[11px] mt-3">
            Grouped by exchange — every position shows its venue tag.
          </div>
        </div>

        <div className="panel w-full lg:w-[280px] flex-shrink-0 flex flex-col items-center">
          <div className="lbl self-start mb-[18px]">Fig 1 · Allocation</div>
          <AllocationDonut positions={positions} />
        </div>
      </div>
    </div>
  )
}
