import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { useState, useMemo, useEffect } from 'react'
import { format } from 'date-fns'
import { GET_POSITION, GET_PORTFOLIO, GET_ASSET_PRICE_HISTORY } from '../graphql/queries'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import RangeSegment, { type RangeKey, rangeToDays } from '../components/common/RangeSegment'
import { assetColor, formatPct, formatTokenPrice, formatUsdPrecise, pnlColorClass } from '../utils/format'
import { excludeCashLikePositions } from '../utils/cashLikeAssets'
import { groupPositionsByAsset, type PositionLike } from '../utils/groupPositionsByAsset'

export default function Position() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [range, setRange] = useState<RangeKey>('90d')
  const [hoveredCandle, setHoveredCandle] = useState<{ timestamp: number; close: number } | null>(
    null,
  )

  const { data: portfolioData } = useQuery(GET_PORTFOLIO)
  const { data, loading, error } = useQuery(GET_POSITION, {
    variables: { id: parseInt(id || '0') },
  })

  const positionSymbol = data?.position?.symbol
  const positionExchange = data?.position?.exchange
  const days = rangeToDays(range)

  useEffect(() => {
    setHoveredCandle(null)
  }, [range, positionSymbol])

  const { data: priceData, loading: priceLoading } = useQuery(GET_ASSET_PRICE_HISTORY, {
    variables: { symbol: positionSymbol || '', days, exchange: positionExchange || null },
    skip: !positionSymbol || !positionExchange,
  })

  const priceHistory = priceData?.assetPriceHistory?.points || []
  const isMock = priceData?.assetPriceHistory?.isMock || false
  const resolutionStatus = priceData?.assetPriceHistory?.resolutionStatus || 'resolved'
  const ambiguityMessage = priceData?.assetPriceHistory?.ambiguityMessage
  const candidates = priceData?.assetPriceHistory?.candidates || []

  const ordersInRange = useMemo(() => {
    const positionOrders = data?.position?.orders || []
    if (priceHistory.length === 0) return positionOrders
    const start = new Date(priceHistory[0].timestamp).getTime()
    const end = new Date(priceHistory[priceHistory.length - 1].timestamp).getTime()
    return positionOrders.filter((order: { executedAt: string }) => {
      const ts = new Date(order.executedAt).getTime()
      return ts >= start && ts <= end
    })
  }, [data?.position?.orders, priceHistory])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading position data…</div>
      </div>
    )
  }

  if (error || !data?.position) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-down font-mono text-sm">Error loading position data</div>
      </div>
    )
  }

  const position = data.position
  const assetTabs = groupPositionsByAsset(
    excludeCashLikePositions((portfolioData?.portfolio?.positions || []) as PositionLike[]),
  )
  const costBasis = position.avgEntryPrice * position.quantity
  const cashInTrade = position.metrics?.cashInTrade ?? 0
  const realisedPnl = position.metrics?.realisedPnl ?? 0
  const unrealized = position.pnl || 0
  const isPositive = unrealized >= 0

  const orders = [...(position.orders || [])].sort(
    (a, b) => new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime(),
  )

  // Prefer earliest buy fill for this venue; fall back to position open date.
  const firstBoughtAt =
    orders
      .filter((o) => o.type === 'buy')
      .reduce<string | null>((earliest, o) => {
        if (!earliest || new Date(o.executedAt) < new Date(earliest)) return o.executedAt
        return earliest
      }, null) ?? position.firstBoughtAt
  const durationDays = firstBoughtAt
    ? Math.max(
        0,
        Math.floor((Date.now() - new Date(firstBoughtAt).getTime()) / (1000 * 60 * 60 * 24)),
      )
    : position.durationDays || 0

  return (
    <div>
      <div className="page-head mb-4">
        <div className="min-w-0">
          <div className="lbl">§2 · Position detail</div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <div className="page-title mt-0">{position.symbol}</div>
            {position.exchange && <span className="chip">{position.exchange}</span>}
            {position.tag?.name && <span className="chip">{position.tag.name}</span>}
            <Link
              to={`/asset/${encodeURIComponent(position.symbol)}`}
              className="font-mono text-[11px] text-sillage-soft hover:text-sillage-ink no-underline"
            >
              all venues ↗
            </Link>
          </div>
        </div>
        <RangeSegment value={range} onChange={setRange} />
      </div>

      <div className="flex gap-2 flex-wrap mb-[18px] overflow-x-auto pb-0.5 -mx-0.5 px-0.5">
        {assetTabs.map((tab, i) => (
          <button
            key={tab.symbol}
            type="button"
            className={`atab ${tab.symbol === position.symbol.toUpperCase() ? 'on' : ''}`}
            onClick={() => navigate(`/asset/${encodeURIComponent(tab.symbol)}`)}
          >
            <span className="sw" style={{ background: assetColor(i) }} />
            {tab.symbol}
          </button>
        ))}
      </div>

      <div className="flex gap-4 sm:gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-between sm:items-start mb-3.5">
            <div className="lbl">Fig 2 · Price · order markers</div>
            <div className="font-mono text-[11px] flex gap-x-3 gap-y-1.5 flex-wrap sm:justify-end">
              <span>
                <span className="text-sillage-green font-bold">B</span> buy
              </span>
              <span>
                <span className="text-sillage-accent font-bold">S</span> sell
              </span>
              <span className="text-sillage-soft">
                <span className="text-sillage-green">—</span> avg entry
              </span>
              {position.metrics?.avgExitPrice != null && (
                <span className="text-sillage-soft">
                  <span className="text-sillage-accent">—</span> avg sell
                </span>
              )}
              {hoveredCandle ? (
                <span className="text-sillage-ink tabular-nums">
                  {format(new Date(hoveredCandle.timestamp), 'MMM dd, yyyy')} ·{' '}
                  {formatTokenPrice(hoveredCandle.close)}
                </span>
              ) : (
                position.currentPrice && (
                  <span className="text-sillage-soft">
                    last {formatTokenPrice(position.currentPrice)}
                  </span>
                )
              )}
            </div>
          </div>
          <AssetPriceChart
            symbol={position.symbol}
            priceHistory={priceHistory}
            orders={ordersInRange}
            avgEntryPrice={position.avgEntryPrice}
            avgExitPrice={position.metrics?.avgExitPrice}
            isMock={isMock}
            loading={priceLoading}
            resolutionStatus={resolutionStatus}
            ambiguityMessage={ambiguityMessage}
            candidates={candidates}
            onCandleHover={setHoveredCandle}
          />
        </div>

        <div className="panel w-full lg:w-[286px] flex-shrink-0">
          <div className="lbl mb-4">P&amp;L · since first entry</div>
          <div className={`font-serif text-[26px] sm:text-[30px] leading-none ${pnlColorClass(unrealized)}`}>
            {isPositive ? '+' : ''}
            {formatUsdPrecise(unrealized)}
          </div>
          <div className={`font-mono text-xs mt-1.5 ${pnlColorClass(position.pnlPercent || 0)}`}>
            {formatPct(position.pnlPercent || 0)} unrealized
          </div>

          <div className="border-t border-sillage-line mt-[18px]">
            {(
              [
                ['Market value', formatUsdPrecise(position.value)],
                ['Cost basis', formatUsdPrecise(costBasis)],
                ['Cash in trade', formatUsdPrecise(cashInTrade)],
                [
                  'Realised P&L',
                  `${realisedPnl >= 0 ? '+' : ''}${formatUsdPrecise(realisedPnl)}`,
                  pnlColorClass(realisedPnl),
                ],
                ['Avg entry', formatTokenPrice(position.avgEntryPrice)],
                ...(position.metrics?.avgExitPrice != null
                  ? [['Avg sell', formatTokenPrice(position.metrics.avgExitPrice)] as const]
                  : []),
                ['Holdings', position.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })],
                ['Duration', `${durationDays} days`],
              ] as [string, string, string?][]
            ).map(([label, val, valClass], idx, arr) => (
              <div
                key={label}
                className={`flex justify-between gap-3 py-2.5 ${idx < arr.length - 1 ? 'border-b border-sillage-line' : ''}`}
              >
                <span className="lbl flex-shrink-0">{label}</span>
                <span className={`font-mono tabular-nums text-xs text-right break-all ${valClass ?? ''}`}>
                  {val}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-4 bg-sillage-gsoft border border-sillage-line rounded-lg px-[15px] py-3">
            <div className="lbl mb-[7px]">
              {position.tag?.name
                ? `Thesis · ${position.tag.name}`
                : `Since · ${position.exchange || 'unknown venue'}`}
            </div>
            <div className="cap leading-relaxed">
              {firstBoughtAt
                ? `First bought {format(new Date(position.firstBoughtAt), 'MMM dd, yyyy')}. `
                : ''}
              Track conviction tags in the Theses view.
              {position.tag?.description
                ? ` ${position.tag.description}`
                : position.tag
                  ? ' Tagged for separate tracking on Theses.'
                  : ' Assign a conviction tag in Settings to track this thesis separately.'}
            </div>
          </div>
        </div>
      </div>

      <div className="panel mt-4 sm:mt-5">
        <div className="lbl mb-1">Table 2 · Order history</div>
        <div className="table-scroll">
          <div className="table-scroll-inner">
            <div className="trow text-sillage-soft border-t-0">
              <div className="w-24 lbl text-[9px]">Date</div>
              <div className="w-[54px] lbl text-[9px]">Side</div>
              <div className="flex-1 lbl text-[9px]">Quantity</div>
              <div className="w-24 text-right lbl text-[9px]">Price</div>
              <div className="w-24 text-right lbl text-[9px]">Value</div>
              <div className="w-24 text-right lbl text-[9px]">Venue</div>
            </div>
            {orders.length === 0 ? (
              <div className="text-center py-8 text-sillage-soft text-sm">No orders found</div>
            ) : (
              orders.map((order) => {
                const isBuy = order.type === 'buy'
                const total = order.quantity * order.price
                return (
                  <div key={order.id} className="trow">
                    <div className="w-24 font-mono text-[11px] text-sillage-soft">
                      {format(new Date(order.executedAt), 'MMM dd, yy')}
                    </div>
                    <div className="w-[54px]">
                      <span className={`font-mono text-[11px] ${isBuy ? 'text-sillage-green' : 'text-sillage-accent'}`}>
                        {isBuy ? 'BUY' : 'SELL'}
                      </span>
                    </div>
                    <div className="flex-1 font-mono tabular-nums text-xs">
                      {order.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })} {position.symbol}
                    </div>
                    <div className="w-24 text-right font-mono tabular-nums text-xs">
                      {formatTokenPrice(order.price)}
                    </div>
                    <div className="w-24 text-right font-mono tabular-nums text-xs">
                      {formatUsdPrecise(total)}
                    </div>
                    <div className="w-24 text-right font-mono text-[11px] text-sillage-soft">
                      {order.exchange || '—'}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 text-center">
        <Link to="/" className="font-mono text-xs text-sillage-soft hover:text-sillage-ink">
          ← back to overview
        </Link>
      </div>
    </div>
  )
}
