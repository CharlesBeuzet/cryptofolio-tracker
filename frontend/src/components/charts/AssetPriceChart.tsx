import { useMemo } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { format } from 'date-fns'
import { formatUsdPrecise } from '../../utils/format'

interface PricePoint {
  timestamp: string
  price: number
}

interface Order {
  executedAt: string
  type: string
  price: number
  quantity: number
}

interface AssetPriceChartProps {
  symbol: string
  priceHistory: PricePoint[]
  orders: Order[]
  avgEntryPrice: number
  avgExitPrice?: number | null
  isMock?: boolean
  loading?: boolean
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
      price: point.price,
      quantity: 0.5 + i * 0.25,
    }
  })
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
}: AssetPriceChartProps) {
  const displayOrders = useMemo(() => {
    if (orders.length > 0) return orders
    if (isMock) return buildDemoOrders(priceHistory)
    return []
  }, [orders, isMock, priceHistory])

  const lineData = useMemo(
    () =>
      priceHistory.map((point) => ({
        timestamp: new Date(point.timestamp).getTime(),
        price: point.price,
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm font-mono">
        Loading price history…
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
    <div className="relative h-[300px] w-full">
      {isMock && (
        <div className="absolute top-0 right-0 z-10 font-mono text-[9px] uppercase tracking-wider text-sillage-soft">
          demo data
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={lineData} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="timestamp"
            type="number"
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
            domain={['auto', 'auto']}
            width={60}
            tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
          />
          <ZAxis range={[80, 80]} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: '11px',
            }}
            labelFormatter={(value) => format(new Date(value), 'MMM dd, yyyy')}
            formatter={(value: number, name: string) => [
              formatUsdPrecise(value),
              name === 'price' ? `${symbol} price` : name,
            ]}
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
          <Line
            type="monotone"
            dataKey="price"
            stroke="var(--green)"
            strokeWidth={1.8}
            dot={false}
            name="price"
          />
          <Scatter
            data={orderData}
            dataKey="price"
            name="orders"
            shape={(props: { cx?: number; cy?: number; payload?: { type: string } }) => (
              <OrderPin {...props} />
            )}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
