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

interface RechartsPriceChartProps {
  symbol: string
  priceHistory: PricePoint[]
  orders: Order[]
  avgEntryPrice: number
}

export default function RechartsPriceChart({
  symbol,
  priceHistory,
  orders,
  avgEntryPrice,
}: RechartsPriceChartProps) {
  const lineData = useMemo(
    () =>
      priceHistory.map((point) => ({
        timestamp: new Date(point.timestamp).getTime(),
        price: point.price,
        label: format(new Date(point.timestamp), 'MMM dd'),
      })),
    [priceHistory],
  )

  const orderData = useMemo(
    () =>
      orders.map((order) => ({
        timestamp: new Date(order.executedAt).getTime(),
        price: order.price,
        type: order.type,
      })),
    [orders],
  )

  if (priceHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm">
        No price data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={lineData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
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
        <ReferenceLine
          y={avgEntryPrice}
          stroke="var(--accent)"
          strokeDasharray="3 3"
          label={{ value: 'Avg', position: 'right', fill: 'var(--soft)', fontSize: 9 }}
        />
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
          shape={(props: { cx?: number; cy?: number; payload?: { type: string } }) => {
            const { cx, cy, payload } = props
            if (cx == null || cy == null) return <></>
            const color = payload?.type === 'sell' ? 'var(--accent)' : 'var(--green)'
            return <circle cx={cx} cy={cy} r={5} fill={color} />
          }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
