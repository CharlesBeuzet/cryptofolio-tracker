import { useMemo, useState, useCallback, useEffect } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Customized,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import { format } from 'date-fns'

interface PricePoint {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  price: number
}

interface Order {
  executedAt: string
  type: string
  price: number
  quantity: number
}

interface CoinGeckoCandidate {
  id: string
  name: string
  symbol: string
}

interface AssetPriceChartProps {
  symbol: string
  priceHistory: PricePoint[]
  orders: Order[]
  avgEntryPrice: number
  avgExitPrice?: number | null
  isMock?: boolean
  loading?: boolean
  resolutionStatus?: string
  ambiguityMessage?: string | null
  candidates?: CoinGeckoCandidate[]
  onCandleHover?: (payload: { timestamp: number; close: number } | null) => void
}

interface CandleDatum {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
}

interface AxisMapEntry {
  scale?: (value: number) => number
}

interface CandlestickLayerProps {
  xAxisMap?: Record<string, AxisMapEntry>
  yAxisMap?: Record<string, AxisMapEntry>
  data?: CandleDatum[]
  offset?: { left?: number; width?: number; height?: number }
  onCandleHover?: (payload: { timestamp: number; close: number } | null) => void
}

function buildDemoOrders(priceHistory: PricePoint[]): Order[] {
  if (priceHistory.length < 4) return []

  const picks = [
    Math.floor(priceHistory.length * 0.15),
    Math.floor(priceHistory.length * 0.4),
    Math.floor(priceHistory.length * 0.62),
    Math.floor(priceHistory.length * 0.85),
  ]

  return picks.map((index, i) => {
    const point = priceHistory[index]
    return {
      executedAt: point.timestamp,
      type: i % 3 === 2 ? 'sell' : 'buy',
      price: point.close,
      quantity: 0.5 + i * 0.25,
    }
  })
}

function computeYDomain(candles: CandleDatum[]): [number, number] {
  const values: number[] = []
  for (const candle of candles) {
    values.push(candle.low, candle.high)
  }

  if (values.length === 0) return [0, 1]

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min
  const pad = span > 0 ? span * 0.06 : Math.max(Math.abs(min) * 0.01, 1)
  return [min - pad, max + pad]
}

function CandlestickLayer({ xAxisMap, yAxisMap, data, offset, onCandleHover }: CandlestickLayerProps) {
  const xAxis = xAxisMap ? Object.values(xAxisMap)[0] : undefined
  const yAxis = yAxisMap ? Object.values(yAxisMap)[0] : undefined
  const xScale = xAxis?.scale
  const yScale = yAxis?.scale

  if (!xScale || !yScale || !data?.length) return null

  const slot =
    data.length > 1
      ? Math.abs(xScale(data[1].timestamp) - xScale(data[0].timestamp))
      : (offset?.width ?? 300) / Math.max(data.length, 1)
  const bodyWidth = Math.max(2, slot * 0.62)

  return (
    <g className="candlestick-layer">
      {data.map((candle) => {
        const x = xScale(candle.timestamp)
        const yHigh = yScale(candle.high)
        const yLow = yScale(candle.low)
        const yOpen = yScale(candle.open)
        const yClose = yScale(candle.close)
        const bullish = candle.close >= candle.open
        const color = bullish ? 'var(--green)' : 'var(--accent)'
        const bodyTop = Math.min(yOpen, yClose)
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1)

        return (
          <g key={candle.timestamp}>
            <rect
              x={x - slot / 2}
              y={0}
              width={slot}
              height={offset?.height ?? 0}
              fill="transparent"
              onMouseEnter={() =>
                onCandleHover?.({ timestamp: candle.timestamp, close: candle.close })
              }
            />
            <line
              x1={x}
              y1={yHigh}
              x2={x}
              y2={yLow}
              stroke={color}
              strokeWidth={1}
              pointerEvents="none"
            />
            <rect
              x={x - bodyWidth / 2}
              y={bodyTop}
              width={bodyWidth}
              height={bodyHeight}
              fill={color}
              stroke={color}
              strokeWidth={0.5}
              pointerEvents="none"
            />
          </g>
        )
      })}
    </g>
  )
}

function OrderPin({
  cx,
  cy,
  payload,
}: {
  cx?: number
  cy?: number
  payload?: { type: string }
}) {
  if (cx == null || cy == null) return null

  const isBuy = payload?.type === 'buy'
  const color = isBuy ? 'var(--green)' : 'var(--accent)'
  const label = isBuy ? 'B' : 'S'

  return (
    <g transform={`translate(${cx}, ${cy - 6})`}>
      <path
        d="M0,-10 C5.5,-10 10,-5.5 10,0 C10,5.5 0,14 0,14 C0,14 -10,5.5 -10,0 C-10,-5.5 -5.5,-10 0,-10 Z"
        fill={color}
        stroke="var(--card)"
        strokeWidth={1.2}
      />
      <text
        x={0}
        y={1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="var(--mkink)"
        fontSize={9}
        fontWeight={700}
        fontFamily="IBM Plex Mono, monospace"
      >
        {label}
      </text>
    </g>
  )
}

export default function AssetPriceChart({
  symbol,
  priceHistory,
  orders,
  avgEntryPrice,
  avgExitPrice,
  isMock = false,
  loading = false,
  resolutionStatus = 'resolved',
  ambiguityMessage,
  candidates = [],
  onCandleHover,
}: AssetPriceChartProps) {
  const [activeTimestamp, setActiveTimestamp] = useState<number | null>(null)

  const handleCandleHover = useCallback(
    (payload: { timestamp: number; close: number } | null) => {
      setActiveTimestamp(payload?.timestamp ?? null)
      onCandleHover?.(payload)
    },
    [onCandleHover],
  )

  const handleChartMouseLeave = useCallback(() => {
    setActiveTimestamp(null)
    onCandleHover?.(null)
  }, [onCandleHover])

  const displayOrders = useMemo(() => {
    if (orders.length > 0) return orders
    if (isMock) return buildDemoOrders(priceHistory)
    return []
  }, [orders, isMock, priceHistory])

  const candleData = useMemo<CandleDatum[]>(
    () =>
      priceHistory.map((point) => ({
        timestamp: new Date(point.timestamp).getTime(),
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
      })),
    [priceHistory],
  )

  const orderData = useMemo(
    () =>
      displayOrders.map((order) => ({
        timestamp: new Date(order.executedAt).getTime(),
        price: order.price,
        type: order.type,
      })),
    [displayOrders],
  )

  const yDomain = useMemo(() => computeYDomain(candleData), [candleData])

  useEffect(() => {
    setActiveTimestamp(null)
  }, [candleData])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm font-mono">
        Loading price history…
      </div>
    )
  }

  if (resolutionStatus === 'ambiguous' || resolutionStatus === 'not_found') {
    return (
      <div className="flex flex-col justify-center h-[300px] px-2">
        <div className="lbl mb-2">
          {resolutionStatus === 'ambiguous' ? 'Ambiguous symbol' : 'Symbol not found'}
        </div>
        <p className="font-mono text-xs text-sillage-soft leading-relaxed max-w-xl">
          {ambiguityMessage || `Unable to load price history for ${symbol}.`}
        </p>
        {candidates.length > 0 && (
          <div className="mt-4 border-t border-sillage-line pt-3">
            <div className="lbl mb-2">Matching assets</div>
            <div className="space-y-2 max-h-[140px] overflow-y-auto">
              {candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  className="flex justify-between gap-3 font-mono text-[11px] border-b border-sillage-line pb-2 last:border-b-0"
                >
                  <span className="text-sillage-ink">{candidate.name}</span>
                  <span className="text-sillage-soft shrink-0">{candidate.id}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (priceHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm">
        No price data available
      </div>
    )
  }

  return (
    <div
      className="relative h-[300px] w-full"
      onMouseLeave={handleChartMouseLeave}
    >
      {isMock && (
        <div className="absolute top-0 right-0 z-10 font-mono text-[9px] uppercase tracking-wider text-sillage-soft">
          demo data
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={candleData} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="timestamp"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value) => format(new Date(value), 'MMM dd')}
            tick={{ fill: 'var(--soft)', fontSize: 9, fontFamily: 'IBM Plex Mono, monospace' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: 'var(--soft)', fontSize: 9, fontFamily: 'IBM Plex Mono, monospace' }}
            axisLine={false}
            tickLine={false}
            domain={yDomain}
            width={60}
            tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
          />
          {avgEntryPrice > 0 && (
            <ReferenceLine
              y={avgEntryPrice}
              stroke="var(--green)"
              strokeDasharray="4 4"
              label={{
                value: 'Avg entry',
                position: 'insideTopRight',
                fill: 'var(--green)',
                fontSize: 9,
                fontFamily: 'IBM Plex Mono, monospace',
              }}
            />
          )}
          {avgExitPrice != null && avgExitPrice > 0 && (
            <ReferenceLine
              y={avgExitPrice}
              stroke="var(--accent)"
              strokeDasharray="4 4"
              label={{
                value: 'Avg sell',
                position: 'insideBottomRight',
                fill: 'var(--accent)',
                fontSize: 9,
                fontFamily: 'IBM Plex Mono, monospace',
              }}
            />
          )}
          <Customized
            component={(props: CandlestickLayerProps) => (
              <CandlestickLayer {...props} onCandleHover={handleCandleHover} />
            )}
          />
          {activeTimestamp != null && (
            <ReferenceLine
              x={activeTimestamp}
              stroke="var(--soft)"
              strokeWidth={1}
              strokeOpacity={0.55}
              ifOverflow="extendDomain"
            />
          )}
          <Line
            type="monotone"
            dataKey="close"
            stroke="transparent"
            dot={false}
            activeDot={false}
            style={{ pointerEvents: 'none' }}
            name="close"
          />
          <Line
            type="monotone"
            dataKey="open"
            stroke="transparent"
            dot={false}
            activeDot={false}
            style={{ pointerEvents: 'none' }}
            name="open"
          />
          <Line
            type="monotone"
            dataKey="high"
            stroke="transparent"
            dot={false}
            activeDot={false}
            style={{ pointerEvents: 'none' }}
            name="high"
          />
          <Line
            type="monotone"
            dataKey="low"
            stroke="transparent"
            dot={false}
            activeDot={false}
            style={{ pointerEvents: 'none' }}
            name="low"
          />
          {orderData.map((order, index) => (
            <ReferenceDot
              key={`${order.timestamp}-${order.type}-${index}`}
              x={order.timestamp}
              y={order.price}
              isFront
              shape={(props: { cx?: number; cy?: number }) => (
                <OrderPin cx={props.cx} cy={props.cy} payload={{ type: order.type }} />
              )}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
