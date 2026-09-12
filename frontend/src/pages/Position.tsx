import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@apollo/client'
import { useState, useMemo, useEffect } from 'react'
import { format } from 'date-fns'
import { GET_POSITION, GET_PORTFOLIO, GET_ASSET_PRICE_HISTORY } from '../graphql/queries'
import { ADD_POSITION_VALUATION, DELETE_POSITION_VALUATION } from '../graphql/mutations'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import PortfolioValueChart from '../components/charts/PortfolioValueChart'
import ValuationTable from '../components/portfolio/ValuationTable'
import AssetSwitcher from '../components/common/AssetSwitcher'
import RangeSegment, { type RangeKey, rangeToDays } from '../components/common/RangeSegment'
import { formatPct, formatTokenPrice, formatUsdPrecise, pnlColorClass } from '../utils/format'
import { excludeCashLikePositions } from '../utils/cashLikeAssets'
import { groupPositionsByAsset, type PositionLike } from '../utils/groupPositionsByAsset'

export default function Position() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [range, setRange] = useState<RangeKey>('90d')
  const [hoveredCandle, setHoveredCandle] = useState<{ timestamp: number; close: number } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)

  const { data: portfolioData } = useQuery(GET_PORTFOLIO)
  const { data, loading, error, refetch } = useQuery(GET_POSITION, {
    variables: { id: parseInt(id || '0') },
  })
  const [addValuation] = useMutation(ADD_POSITION_VALUATION)
  const [deleteValuation] = useMutation(DELETE_POSITION_VALUATION)

  const positionSymbol = data?.position?.symbol
  const positionExchange = data?.position?.exchange
  const isManual = data?.position?.source === 'manual'
  const days = rangeToDays(range)

  useEffect(() => {
    setHoveredCandle(null)
  }, [range, positionSymbol])

  const { data: priceData, loading: priceLoading } = useQuery(GET_ASSET_PRICE_HISTORY, {
    variables: { symbol: positionSymbol || '', days, exchange: positionExchange || null },
    skip: !positionSymbol || !positionExchange || isManual,
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
  const costBasis = position.costBasis ?? position.avgEntryPrice * position.quantity
  const cashInTrade = position.metrics?.cashInTrade ?? 0
  const realisedPnl = position.metrics?.realisedPnl ?? 0
  const unrealized = position.pnl || 0
  const isPositive = unrealized >= 0
  const title = isManual && position.displayName ? position.displayName : position.symbol

  const orders = [...(position.orders || [])].sort(
    (a: { executedAt: string }, b: { executedAt: string }) =>
      new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime(),
  )

  const valuations = position.valuations || []
  const chartHistory = [...valuations]
    .sort(
      (a: { recordedAt: string }, b: { recordedAt: string }) =>
        new Date(a.recordedAt).getTime() - new Date(b.recordedAt).getTime(),
    )
    .map((v: { recordedAt: string; valueAmount: number }) => ({
      timestamp: v.recordedAt,
      totalValue: v.valueAmount,
    }))

  const firstBoughtAt =
    orders
      .filter((o: { type: string }) => o.type === 'buy')
      .reduce<string | null>((earliest: string | null, o: { executedAt: string }) => {
        if (!earliest || new Date(o.executedAt) < new Date(earliest)) return o.executedAt
        return earliest
      }, null) ??
    (valuations.length
      ? [...valuations].sort(
          (a: { recordedAt: string }, b: { recordedAt: string }) =>
            new Date(a.recordedAt).getTime() - new Date(b.recordedAt).getTime(),
        )[0].recordedAt
      : position.firstBoughtAt)
  const durationDays = firstBoughtAt
    ? Math.max(
        0,
        Math.floor((Date.now() - new Date(firstBoughtAt).getTime()) / (1000 * 60 * 60 * 24)),
      )
    : position.durationDays || 0

  const onAddValuation = async (input: {
    recordedAt: string
    valueAmount: number
    quantity: number | null
  }) => {
    setBusy(true)
    try {
      await addValuation({
        variables: {
          positionId: position.id,
          valueAmount: input.valueAmount,
          recordedAt: input.recordedAt,
          quantity: input.quantity,
        },
        refetchQueries: ['GetPortfolio', 'GetPosition'],
      })
      await refetch()
    } finally {
      setBusy(false)
    }
  }

  const onDeleteValuation = async (valuationId: number) => {
    if (!window.confirm('Delete this valuation?')) return
    setBusy(true)
    try {
      await deleteValuation({
        variables: { id: valuationId },
        refetchQueries: ['GetPortfolio', 'GetPosition'],
      })
      await refetch()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="page-head mb-4">
        <div className="min-w-0">
          <div className="lbl">§2 · Position detail</div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <div className="page-title mt-0">{title}</div>
            {isManual && position.symbol && position.displayName && (
              <span className="tk text-sillage-soft">{position.symbol}</span>
            )}
            {position.exchange && <span className="chip">{position.exchange}</span>}
            {isManual && <span className="chip manual">manual</span>}
            {position.tag?.name && <span className="chip">{position.tag.name}</span>}
            {isManual && position.externalUrl && (
              <a
                href={position.externalUrl}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-[11px] text-sillage-soft hover:text-sillage-ink no-underline"
              >
                open link ↗
              </a>
            )}
            <Link
              to={`/asset/${encodeURIComponent(position.symbol)}`}
              className="font-mono text-[11px] text-sillage-soft hover:text-sillage-ink no-underline"
            >
              all venues ↗
            </Link>
          </div>
        </div>
        {!isManual && <RangeSegment value={range} onChange={setRange} />}
      </div>

      <AssetSwitcher
        assets={assetTabs}
        currentSymbol={position.symbol}
        onSelect={(symbol) => navigate(`/asset/${encodeURIComponent(symbol)}`)}
      />

      <div className="flex gap-4 sm:gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          {isManual ? (
            <>
              <div className="flex flex-col gap-2 sm:flex-row sm:justify-between sm:items-start mb-3.5">
                <div className="lbl">Fig 2 · Mark-to-market</div>
                <div className="font-mono text-[11px] text-sillage-soft">
                  last {formatUsdPrecise(position.value)}
                </div>
              </div>
              <div className="h-[220px]">
                <PortfolioValueChart data={chartHistory} height="100%" valueLabel="Value" />
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
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
                ...(isManual
                  ? []
                  : [
                      ['Cash in trade', formatUsdPrecise(cashInTrade)] as [string, string, string?],
                      [
                        'Realised P&L',
                        `${realisedPnl >= 0 ? '+' : ''}${formatUsdPrecise(realisedPnl)}`,
                        pnlColorClass(realisedPnl),
                      ] as [string, string, string?],
                      ['Avg entry', formatTokenPrice(position.avgEntryPrice)] as [
                        string,
                        string,
                        string?,
                      ],
                      ...(position.metrics?.avgExitPrice != null
                        ? ([
                            ['Avg sell', formatTokenPrice(position.metrics.avgExitPrice)],
                          ] as [string, string, string?][])
                        : []),
                    ]),
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
                : isManual
                  ? `Manual · ${position.exchange || 'declared'}`
                  : `Since · ${position.exchange || 'unknown venue'}`}
            </div>
            <div className="cap leading-relaxed">
              {firstBoughtAt
                ? `First ${isManual ? 'marked' : 'bought'} ${format(new Date(firstBoughtAt), 'MMM dd, yyyy')}. `
                : ''}
              {isManual
                ? 'Value is the latest mark you entered. Add snapshots below to keep NAV in line with parked cash.'
                : 'Track conviction tags in the Theses view.'}
              {position.tag?.description
                ? ` ${position.tag.description}`
                : position.tag
                  ? ' Tagged for separate tracking on Theses.'
                  : isManual
                    ? ''
                    : ' Assign a conviction tag in Settings to track this thesis separately.'}
            </div>
          </div>
        </div>
      </div>

      {isManual ? (
        <ValuationTable
          symbol={position.symbol}
          valuations={valuations}
          venue={position.exchange}
          busy={busy}
          onAdd={onAddValuation}
          onDelete={onDeleteValuation}
        />
      ) : (
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
                orders.map(
                  (order: {
                    id: number
                    type: string
                    quantity: number
                    price: number
                    executedAt: string
                    exchange: string | null
                  }) => {
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
                          {position.symbol}
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
                  },
                )
              )}
            </div>
          </div>
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