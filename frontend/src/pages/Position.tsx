import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { useState, useMemo } from 'react'
import { format } from 'date-fns'
import { GET_POSITION, GET_PORTFOLIO, GET_ASSET_PRICE_HISTORY } from '../graphql/queries'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import RangeSegment, { type RangeKey, rangeToDays } from '../components/common/RangeSegment'
import { assetColor, formatPct, formatUsdPrecise, pnlColorClass } from '../utils/format'

export default function Position() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [range, setRange] = useState<RangeKey>('90d')

  const { data: portfolioData } = useQuery(GET_PORTFOLIO)
  const { data, loading, error } = useQuery(GET_POSITION, {
    variables: { id: parseInt(id || '0') },
  })

  const positionSymbol = data?.position?.symbol
  const days = rangeToDays(range)

  const { data: priceData, loading: priceLoading } = useQuery(GET_ASSET_PRICE_HISTORY, {
    variables: { symbol: positionSymbol || '', days },
    skip: !positionSymbol,
  })

  const priceHistory = priceData?.assetPriceHistory?.points || []
  const isMock = priceData?.assetPriceHistory?.isMock || false

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
  const allPositions = [...(portfolioData?.portfolio?.positions || [])].sort((a, b) => b.value - a.value)
  const posIndex = allPositions.findIndex((p) => p.id === position.id)
  const costBasis = position.avgEntryPrice * position.quantity
  const unrealized = position.pnl || 0
  const isPositive = unrealized >= 0

  const orders = [...(position.orders || [])].sort(
    (a, b) => new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime(),
  )

  return (
    <div>
      <div className="flex justify-between items-end mb-4">
        <div>
          <div className="lbl">§2 · Position detail</div>
          <div className="flex items-center gap-3 mt-2">
            <div className="font-serif text-[26px] leading-none">{position.symbol}</div>
            {position.exchange && <span className="chip">{position.exchange}</span>}
          </div>
        </div>
        <RangeSegment value={range} onChange={setRange} />
      </div>

      <div className="flex gap-2.5 flex-wrap mb-[18px]">
        {allPositions.map((p, i) => (
          <button
            key={p.id}
            type="button"
            className={`atab ${p.id === position.id ? 'on' : ''}`}
            onClick={() => navigate(`/position/${p.id}`)}
          >
            <span className="sw" style={{ background: assetColor(i) }} />
            {p.symbol}
          </button>
        ))}
      </div>

      <div className="flex gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          <div className="flex justify-between items-center mb-3.5">
            <div className="lbl">Fig 2 · Price · order markers</div>
            <div className="font-mono text-[11px] flex gap-4 flex-wrap justify-end">
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
              {position.currentPrice && (
                <span className="text-sillage-soft">
                  last {formatUsdPrecise(position.currentPrice)}
                </span>
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
          />
        </div>

        <div className="panel w-full lg:w-[286px] flex-shrink-0">
          <div className="lbl mb-4">P&amp;L · since first entry</div>
          <div className={`font-serif text-[30px] leading-none ${pnlColorClass(unrealized)}`}>
            {isPositive ? '+' : ''}
            {formatUsdPrecise(unrealized)}
          </div>
          <div className={`font-mono text-xs mt-1.5 ${pnlColorClass(position.pnlPercent || 0)}`}>
            {formatPct(position.pnlPercent || 0)} unrealized
          </div>

          <div className="border-t border-sillage-line mt-[18px]">
            {[
              ['Market value', formatUsdPrecise(position.value)],
              ['Cost basis', formatUsdPrecise(costBasis)],
              ['Avg entry', formatUsdPrecise(position.avgEntryPrice)],
              ...(position.metrics?.avgExitPrice != null
                ? [['Avg sell', formatUsdPrecise(position.metrics.avgExitPrice)] as const]
                : []),
              ['Holdings', position.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })],
              ['Duration', `${position.durationDays} days`],
            ].map(([label, val], idx, arr) => (
              <div
                key={label}
                className={`flex justify-between py-2.5 ${idx < arr.length - 1 ? 'border-b border-sillage-line' : ''}`}
              >
                <span className="lbl">{label}</span>
                <span className="font-mono tabular-nums text-xs">{val}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 bg-sillage-gsoft border border-sillage-line rounded-lg px-[15px] py-3">
            <div className="lbl mb-[7px]">Since · {position.exchange || 'unknown venue'}</div>
            <div className="cap leading-relaxed">
              First bought {format(new Date(position.firstBoughtAt), 'MMM dd, yyyy')}. Track conviction
              tags in the Theses view.
            </div>
          </div>
        </div>
      </div>

      <div className="panel mt-5">
        <div className="lbl mb-1">Table 2 · Order history</div>
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
                  {formatUsdPrecise(order.price)}
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

      {posIndex > 0 && (
        <div className="mt-4 text-center">
          <Link to="/" className="font-mono text-xs text-sillage-soft hover:text-sillage-ink">
            ← back to overview
          </Link>
        </div>
      )}
    </div>
  )
}
