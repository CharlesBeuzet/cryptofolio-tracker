import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { Fragment, useState, useMemo, useEffect } from 'react'
import { format } from 'date-fns'
import { GET_ASSET, GET_PORTFOLIO, GET_ASSET_PRICE_HISTORY } from '../graphql/queries'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import PortfolioValueChart from '../components/charts/PortfolioValueChart'
import ValuationTable from '../components/portfolio/ValuationTable'
import RangeSegment, { type RangeKey, rangeToDays } from '../components/common/RangeSegment'
import { assetColor, formatPct, formatTokenPrice, formatUsdPrecise, pnlColorClass } from '../utils/format'
import { groupPositionsByAsset } from '../utils/groupPositionsByAsset'

interface AssetOrder {
  id: number
  symbol: string
  type: string
  quantity: number
  price: number
  executedAt: string
  exchange: string | null
}

export default function Asset() {
  const { symbol: rawSymbol } = useParams<{ symbol: string }>()
  const symbol = decodeURIComponent(rawSymbol || '').toUpperCase()
  const navigate = useNavigate()
  const [range, setRange] = useState<RangeKey>('90d')
  const [hoveredCandle, setHoveredCandle] = useState<{ timestamp: number; close: number } | null>(
    null,
  )

  const { data: portfolioData } = useQuery(GET_PORTFOLIO)
  const { data, loading, error } = useQuery(GET_ASSET, {
    variables: { symbol },
    skip: !symbol,
  })

  const assetData = data?.asset
  const venues = assetData?.positions || []
  const grouped = useMemo(() => groupPositionsByAsset(venues), [venues])
  const asset = grouped[0]
  const allManual =
    venues.length > 0 && venues.every((p: { source?: string }) => p.source === 'manual')

  const primaryExchange =
    venues.find((p: { id: number }) => p.id === asset?.primaryId)?.exchange ||
    venues[0]?.exchange ||
    (assetData?.orders || []).find((o: { exchange?: string | null }) => o.exchange)?.exchange ||
    null
  const days = rangeToDays(range)

  useEffect(() => {
    setHoveredCandle(null)
  }, [range, symbol])

  const { data: priceData, loading: priceLoading } = useQuery(GET_ASSET_PRICE_HISTORY, {
    variables: { symbol, days, exchange: primaryExchange },
    skip: !symbol || !primaryExchange || allManual,
  })

  const priceHistory = priceData?.assetPriceHistory?.points || []
  const isMock = priceData?.assetPriceHistory?.isMock || false
  const resolutionStatus = priceData?.assetPriceHistory?.resolutionStatus || 'resolved'
  const ambiguityMessage = priceData?.assetPriceHistory?.ambiguityMessage
  const candidates = priceData?.assetPriceHistory?.candidates || []

  const allOrders: AssetOrder[] = useMemo(() => {
    const orders = [...(assetData?.orders || [])] as AssetOrder[]
    return orders.sort(
      (a, b) => new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime(),
    )
  }, [assetData?.orders])

  const ordersInRange = useMemo(() => {
    if (priceHistory.length === 0) return allOrders
    const start = new Date(priceHistory[0].timestamp).getTime()
    const end = new Date(priceHistory[priceHistory.length - 1].timestamp).getTime()
    return allOrders.filter((order) => {
      const ts = new Date(order.executedAt).getTime()
      return ts >= start && ts <= end
    })
  }, [allOrders, priceHistory])

  const avgExitPrice = useMemo(() => {
    const sells = allOrders.filter((o) => o.type === 'sell')
    const qty = sells.reduce((s, o) => s + o.quantity, 0)
    if (qty <= 0) return null
    const proceeds = sells.reduce((s, o) => s + o.quantity * o.price, 0)
    return proceeds / qty
  }, [allOrders])

  const assetTabs = useMemo(() => {
    const positions = portfolioData?.portfolio?.positions || []
    return groupPositionsByAsset(positions)
  }, [portfolioData?.portfolio?.positions])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading asset data…</div>
      </div>
    )
  }

  if (error || !assetData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-down font-mono text-sm">Error loading asset data</div>
      </div>
    )
  }

  const displaySymbol = asset?.symbol || assetData.symbol || symbol
  const unrealized = asset?.pnl ?? 0
  const isPositive = unrealized >= 0
  const currentPrice = venues[0]?.currentPrice as number | null | undefined
  // Prefer earliest buy fill across all venues; fall back to position open dates.
  const firstBoughtAt =
    allOrders
      .filter((o) => o.type === 'buy')
      .reduce<string | null>((earliest, o) => {
        if (!earliest || new Date(o.executedAt) < new Date(earliest)) return o.executedAt
        return earliest
      }, null) ??
    venues.reduce((earliest: string | null, p: { firstBoughtAt: string }) => {
      if (!earliest || new Date(p.firstBoughtAt) < new Date(earliest)) return p.firstBoughtAt
      return earliest
    }, null as string | null)
  const durationDays = firstBoughtAt
    ? Math.max(
        0,
        Math.floor((Date.now() - new Date(firstBoughtAt).getTime()) / (1000 * 60 * 60 * 24)),
      )
    : Math.max(0, ...venues.map((p: { durationDays: number }) => p.durationDays || 0))

  const venueChips = asset?.venues?.length
    ? asset.venues
    : Array.from(
        new Map(
          allOrders
            .filter((o) => o.exchange)
            .map((o) => [
              o.exchange!.toLowerCase(),
              { id: o.id, exchange: o.exchange!, source: 'synced' as const },
            ]),
        ).values(),
      )

  const venueLabel =
    venueChips.length > 1
      ? `${venueChips.length} venues`
      : venueChips[0]?.exchange || 'unknown venue'

  const avgEntryPrice = asset?.avgEntryPrice ?? 0
  const costBasis = asset?.costBasis ?? 0
  const marketValue = asset?.value ?? 0
  const holdings = asset?.quantity ?? 0

  return (
    <div>
      <div className="flex justify-between items-end mb-4">
        <div>
          <div className="lbl">§2 · Asset detail</div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <div className="font-serif text-[26px] leading-none">{displaySymbol}</div>
            {venueChips.map((venue) => (
              <Fragment key={venue.id}>
              <span
                role={asset ? 'link' : undefined}
                tabIndex={asset ? 0 : undefined}
                className={asset ? 'chip cl' : 'chip'}
                onClick={
                  asset
                    ? () => navigate(`/position/${venue.id}`)
                    : undefined
                }
                onKeyDown={
                  asset
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          navigate(`/position/${venue.id}`)
                        }
                      }
                    : undefined
                }
              >
                {venue.exchange}
              </span>
              {venue.source === 'manual' && <span className="chip manual">manual</span>}
              </Fragment>
            ))}
          </div>
        </div>
        {!allManual && <RangeSegment value={range} onChange={setRange} />}
      </div>

      <div className="flex gap-2.5 flex-wrap mb-[18px]">
        {assetTabs.map((tab, i) => (
          <button
            key={tab.symbol}
            type="button"
            className={`atab ${tab.symbol === displaySymbol ? 'on' : ''}`}
            onClick={() => navigate(`/asset/${encodeURIComponent(tab.symbol)}`)}
          >
            <span className="sw" style={{ background: assetColor(i) }} />
            {tab.symbol}
          </button>
        ))}
      </div>

      <div className="flex gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          {allManual ? (
            <>
              <div className="flex justify-between items-center mb-3.5">
                <div className="lbl">Fig 2 · Mark-to-market</div>
                <div className="font-mono text-[11px] text-sillage-soft">
                  last {formatUsdPrecise(marketValue)}
                </div>
              </div>
              <div className="h-[220px]">
                <PortfolioValueChart
                  data={[...(venues[0]?.valuations || [])]
                    .sort(
                      (
                        a: { recordedAt: string },
                        b: { recordedAt: string },
                      ) => new Date(a.recordedAt).getTime() - new Date(b.recordedAt).getTime(),
                    )
                    .map((v: { recordedAt: string; valueAmount: number }) => ({
                      timestamp: v.recordedAt,
                      totalValue: v.valueAmount,
                    }))}
                  height="100%"
                  valueLabel="Value"
                />
              </div>
            </>
          ) : (
            <>
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
                  {avgExitPrice != null && (
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
                    currentPrice != null && (
                      <span className="text-sillage-soft">last {formatTokenPrice(currentPrice)}</span>
                    )
                  )}
                </div>
              </div>
              <AssetPriceChart
                symbol={displaySymbol}
                priceHistory={priceHistory}
                orders={ordersInRange}
                avgEntryPrice={avgEntryPrice}
                avgExitPrice={avgExitPrice}
                isMock={isMock}
                loading={priceLoading}
                resolutionStatus={resolutionStatus}
                ambiguityMessage={ambiguityMessage}
                candidates={candidates}
                onCandleHover={setHoveredCandle}
              />
            </>
          )}
        </div>

        <div className="panel w-full lg:w-[286px] flex-shrink-0">
          <div className="lbl mb-4">P&amp;L · consolidated</div>
          <div className={`font-serif text-[30px] leading-none ${pnlColorClass(unrealized)}`}>
            {isPositive ? '+' : ''}
            {formatUsdPrecise(unrealized)}
          </div>
          <div className={`font-mono text-xs mt-1.5 ${pnlColorClass(asset?.pnlPercent ?? 0)}`}>
            {formatPct(asset?.pnlPercent ?? 0)} unrealized
          </div>

          <div className="border-t border-sillage-line mt-[18px]">
            {[
              ['Market value', formatUsdPrecise(marketValue)],
              ['Cost basis', formatUsdPrecise(costBasis)],
              ...(allManual
                ? []
                : [
                    ['Avg entry', formatTokenPrice(avgEntryPrice)] as const,
                    ...(avgExitPrice != null
                      ? [['Avg sell', formatTokenPrice(avgExitPrice)] as const]
                      : []),
                  ]),
              [
                'Holdings',
                holdings.toLocaleString(undefined, { maximumFractionDigits: 8 }),
              ],
              ['Duration', `${durationDays} days`],
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
            <div className="lbl mb-[7px]">Across · {venueLabel}</div>
            <div className="cap leading-relaxed">
              {firstBoughtAt
                ? `First ${allManual ? 'marked' : 'bought'} ${format(new Date(firstBoughtAt), 'MMM dd, yyyy')}. `
                : ''}
              {allManual
                ? 'Click a venue tag to add valuation snapshots for a single declared holding.'
                : 'Orders below include every venue that traded this asset. Click a venue tag for a single-exchange view.'}
            </div>
          </div>
        </div>
      </div>

      {allManual ? (
        venues.map(
          (venue: {
            id: number
            exchange: string | null
            valuations?: Array<{
              id: number
              recordedAt: string
              valueAmount: number
              quantity: number | null
            }>
          }) => (
            <ValuationTable
              key={venue.id}
              symbol={displaySymbol}
              valuations={venue.valuations || []}
              venue={venue.exchange}
              showVenue
            />
          ),
        )
      ) : (
      <div className="panel mt-5">
        <div className="lbl mb-1">Table 2 · Consolidated order history</div>
        <div className="trow text-sillage-soft border-t-0">
          <div className="w-24 lbl text-[9px]">Date</div>
          <div className="w-[54px] lbl text-[9px]">Side</div>
          <div className="flex-1 lbl text-[9px]">Quantity</div>
          <div className="w-24 text-right lbl text-[9px]">Price</div>
          <div className="w-24 text-right lbl text-[9px]">Value</div>
          <div className="w-24 text-right lbl text-[9px]">Venue</div>
        </div>
        {allOrders.length === 0 ? (
          <div className="text-center py-8 text-sillage-soft text-sm">No orders found</div>
        ) : (
          allOrders.map((order) => {
            const isBuy = order.type === 'buy'
            const total = order.quantity * order.price
            return (
              <div key={order.id} className="trow">
                <div className="w-24 font-mono text-[11px] text-sillage-soft">
                  {format(new Date(order.executedAt), 'MMM dd, yy')}
                </div>
                <div className="w-[54px]">
                  <span
                    className={`font-mono text-[11px] ${isBuy ? 'text-sillage-green' : 'text-sillage-accent'}`}
                  >
                    {isBuy ? 'BUY' : 'SELL'}
                  </span>
                </div>
                <div className="flex-1 font-mono tabular-nums text-xs">
                  {order.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}{' '}
                  {displaySymbol}
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
      )}

      <div className="mt-4 text-center">
        <Link to="/" className="font-mono text-xs text-sillage-soft hover:text-sillage-ink">
          ← back to overview
        </Link>
      </div>
    </div>
  )
}
