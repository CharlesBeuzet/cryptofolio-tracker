import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { format } from 'date-fns'

interface Order {
  executedAt: string
  type: string
  price: number
  quantity: number
}

interface Position {
  symbol: string
  currentPrice: number | null
  avgEntryPrice: number
  orders: Order[]
}

interface PositionChartProps {
  position: Position
}

export default function PositionChart({ position }: PositionChartProps) {
  const orders = position.orders || []

  const chartData = orders
    .map((order) => ({
      date: format(new Date(order.executedAt), 'MMM dd'),
      price: order.price,
      type: order.type,
    }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

  if (position.currentPrice) {
    chartData.push({
      date: format(new Date(), 'MMM dd'),
      price: position.currentPrice,
      type: 'current',
    })
  }

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm">
        No price data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <CartesianGrid stroke="var(--line)" strokeDasharray="0" vertical={false} />
        <XAxis
          dataKey="date"
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
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--card)',
            border: '1px solid var(--line)',
            borderRadius: '8px',
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '11px',
          }}
          formatter={(value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <ReferenceLine
          y={position.avgEntryPrice}
          stroke="var(--accent)"
          strokeDasharray="3 3"
          label={{ value: 'Avg', position: 'right', fill: 'var(--soft)', fontSize: 9 }}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="var(--green)"
          strokeWidth={1.8}
          dot={(props: { cx?: number; cy?: number; payload?: { type: string } }) => {
            const { cx, cy, payload } = props
            if (cx == null || cy == null) return <></>
            const color =
              payload?.type === 'buy'
                ? 'var(--green)'
                : payload?.type === 'sell'
                  ? 'var(--accent)'
                  : 'var(--soft)'
            return <circle cx={cx} cy={cy} r={5} fill={color} />
          }}
          name="Price"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
