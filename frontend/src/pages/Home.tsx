import { useQuery } from '@apollo/client'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { format } from 'date-fns'
import { GET_PORTFOLIO, GET_PORTFOLIO_HISTORY, GET_FIAT_DEPOSITS_SUMMARY } from '../graphql/queries'
import PortfolioValueChart, { type NavInspectPoint } from '../components/charts/PortfolioValueChart'
import AllocationDonut from '../components/charts/AllocationDonut'
import RangeSegment, { rangeLabel, rangeToDays, type RangeKey } from '../components/common/RangeSegment'
import { isCashLikeAsset } from '../utils/cashLikeAssets'
import { assetColor, formatPct, formatUsd, formatUsdPrecise, pnlColorClass } from '../utils/format'
import { groupPositionsByAsset, type GroupedAsset } from '../utils/groupPositionsByAsset'
import { appendLiveNavPoint } from '../utils/portfolioChart'

function OverviewAssetRow({
  asset,
  index,
  share,
}: {
  asset: GroupedAsset
  index: number
  share: number
}) {
  const navigate = useNavigate()
  const cash = isCashLikeAsset(asset.symbol)

  const inner = (
    <>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="sw" style={{ background: assetColor(index) }} />
          <span className="tk">{asset.symbol}</span>
          {asset.venues.map((venue) => (
            <Fragment key={venue.id}>
              {cash ? (
                <span className="chip">{venue.exchange}</span>
              ) : (
                <span
                  role="link"
                  tabIndex={0}
                  className="chip cl"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    navigate(`/position/${venue.id}`)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      e.stopPropagation()
                      navigate(`/position/${venue.id}`)
                    }
                  }}
                >
                  {venue.exchange}
                </span>
              )}
              {venue.tag?.name && <span className="chip tag">{venue.tag.name}</span>}
            </Fragment>
          ))}
        </div>
        <div className="text-sillage-soft text-[11px] mt-[3px] ml-[18px] font-mono truncate">
          {asset.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}
        </div>
      </div>
      <div className="w-[72px] sm:w-24 text-right font-mono tabular-nums text-[12px] sm:text-[13px] flex-shrink-0">
        {formatUsdPrecise(asset.value)}
      </div>
      <div className="hidden sm:block w-20 flex-shrink-0">
        <div className="wbar">
          <div className="wfill" style={{ width: `${share}%` }} />
        </div>
        <div className="text-sillage-soft font-mono text-[9px] mt-[3px] text-right tabular-nums">
          {share.toFixed(1)}%
        </div>
      </div>
      <div
        className={`w-[62px] sm:w-[74px] text-right font-mono text-[11px] sm:text-xs tabular-nums flex-shrink-0 ${
          cash ? 'text-sillage-soft' : pnlColorClass(asset.pnl)
        }`}
      >
        {cash ? '—' : formatPct(asset.pnlPercent)}
      </div>
    </>
  )

  if (cash) {
    return <div className="hrow hrow-static">{inner}</div>
  }

  return (
    <Link to={`/asset/${encodeURIComponent(asset.symbol)}`} className="hrow no-underline text-inherit">
      {inner}
    </Link>
  )
}

export default function Home() {
  const [range, setRange] = useState<RangeKey>('90d')
  const [inspected, setInspected] = useState<NavInspectPoint | null>(null)
  const navigate = useNavigate()

  const { data: portfolioData, loading: portfolioLoading } = useQuery(GET_PORTFOLIO)
  const { data: historyData, loading: historyLoading } = useQuery(GET_PORTFOLIO_HISTORY, {
    variables: { days: rangeToDays(range) },
  })
  const { data: fiatSummaryData } = useQuery(GET_FIAT_DEPOSITS_SUMMARY)

  useEffect(() => {
    setInspected(null)
  }, [range])

  const rawHistory = historyData?.portfolioHistory
  const liveTotal = portfolioData?.portfolio?.totalValue
  const chartHistory = useMemo(() => {
    const points = rawHistory || []
    return liveTotal != null ? appendLiveNavPoint(points, liveTotal) : points
  }, [rawHistory, liveTotal])

  if (portfolioLoading || historyLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading portfolio data…</div>
      </div>
    )
  }

  const portfolio = portfolioData?.portfolio
  const positions = portfolio?.positions || []
  const totalValue = portfolio?.totalValue || 0
  const assets = groupPositionsByAsset(positions)
  const totalBook = assets.reduce((s, a) => s + a.value, 0)

  const fiatTotal = (fiatSummaryData?.fiatDepositsSummary?.totalsByCurrency || []).reduce(
    (s: number, r: { totalAmount: number }) => s + r.totalAmount,
    0,
  )
  const pnl = totalValue - fiatTotal
  const heroValue = inspected?.totalValue ?? totalValue
  const heroLabel = inspected
    ? format(new Date(inspected.timestamp), 'MMM dd, yyyy')
    : rangeLabel(range)

  return (
    <div>
      <div className="page-head">
        <div className="min-w-0">
          <div className="lbl">§1 · Overview</div>
          <div className="page-title">Consolidated positions</div>
        </div>
        <RangeSegment value={range} onChange={setRange} />
      </div>

      <div className="panel p-0 overflow-hidden relative">
        <div className="px-4 pt-4 sm:px-6 sm:pt-5 lg:absolute lg:left-6 lg:top-5 lg:z-10 lg:pointer-events-none lg:px-0 lg:pt-0">
          <div className="lbl">Net asset value · {heroLabel}</div>
          <div className="font-serif text-[32px] sm:text-[40px] lg:text-[46px] leading-none mt-1.5">
            {formatUsd(heroValue)}
          </div>
          <div className="font-mono text-[11px] sm:text-xs mt-[7px] text-sillage-soft break-words">
            NAV = deposits + P&amp;L ⟶{' '}
            <span className="tabular-nums">{formatUsd(totalValue)}</span> ={' '}
            <span className="tabular-nums">{formatUsd(fiatTotal)}</span> +{' '}
            <span className={`tabular-nums ${pnlColorClass(pnl)}`}>{formatUsd(pnl)}</span>
          </div>
        </div>
        <div className="mt-2 lg:mt-0 h-[200px] sm:h-[250px]">
          <PortfolioValueChart data={chartHistory} height="100%" onPointInspect={setInspected} />
        </div>
      </div>

      <div className="flex gap-4 sm:gap-5 mt-4 sm:mt-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          <div className="flex flex-col gap-1 sm:flex-row sm:justify-between sm:items-baseline mb-1">
            <div className="lbl">Table 1 · Positions by asset</div>
            <div className="cap">tap a row to inspect ↗</div>
          </div>

          {assets.length === 0 ? (
            <div className="text-center py-8 text-sillage-soft text-sm">No positions found</div>
          ) : (
            assets.map((asset, i) => {
              const share = totalBook > 0 ? (asset.value / totalBook) * 100 : 0

              return (
                <Link
                  key={asset.symbol}
                  to={`/asset/${encodeURIComponent(asset.symbol)}`}
                  className="hrow no-underline text-inherit"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="sw" style={{ background: assetColor(i) }} />
                      <span className="tk">{asset.symbol}</span>
                      {asset.venues.map((venue) => (
                        <Fragment key={venue.id}>
                          <span
                            role="link"
                            tabIndex={0}
                            className="chip cl"
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              navigate(`/position/${venue.id}`)
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                e.stopPropagation()
                                navigate(`/position/${venue.id}`)
                              }
                            }}
                          >
                            {venue.exchange}
                          </span>
                          {venue.source === 'manual' && (
                            <span className="chip manual">manual</span>
                          )}
                          {venue.tag?.name && (
                            <span className="chip tag">{venue.tag.name}</span>
                          )}
                        </Fragment>
                      ))}
                    </div>
                    <div className="text-sillage-soft text-[11px] mt-[3px] ml-[18px] font-mono truncate">
                      {asset.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                    </div>
                  </div>
                  <div className="w-[72px] sm:w-24 text-right font-mono tabular-nums text-[12px] sm:text-[13px] flex-shrink-0">
                    {formatUsdPrecise(asset.value)}
                  </div>
                  <div className="hidden sm:block w-20 flex-shrink-0">
                    <div className="wbar">
                      <div className="wfill" style={{ width: `${share}%` }} />
                    </div>
                    <div className="text-sillage-soft font-mono text-[9px] mt-[3px] text-right tabular-nums">
                      {share.toFixed(1)}%
                    </div>
                  </div>
                  <div className={`w-[62px] sm:w-[74px] text-right font-mono text-[11px] sm:text-xs tabular-nums flex-shrink-0 ${pnlColorClass(asset.pnl)}`}>
                    {formatPct(asset.pnlPercent)}
                  </div>
                </Link>
              )
              return <OverviewAssetRow key={asset.symbol} asset={asset} index={i} share={share} />
            })
          )}

          <div className="rule mt-3" />
          <div className="font-mono text-sillage-soft text-[11px] mt-3">
            Grouped by asset — venue tags show every exchange holding the same coin.
          </div>
        </div>

        <div className="panel w-full lg:w-[280px] flex-shrink-0 flex flex-col items-center">
          <div className="lbl self-start mb-[18px]">Fig 1 · Allocation</div>
          <AllocationDonut positions={assets} />
        </div>
      </div>
    </div>
  )
}
