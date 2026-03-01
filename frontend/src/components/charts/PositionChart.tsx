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
  // Generate price data points (simplified - in real app, fetch historical price data)
  // For V0, we'll create a simple chart showing buy/sell markers
  const orders = position.orders || []
  
  // Create chart data from orders
  const chartData = orders
    .map((order) => ({
      date: format(new Date(order.executedAt), 'MMM dd, yyyy'),
      price: order.price,
      type: order.type,
    }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

  // Add current price point
  if (position.currentPrice) {
    chartData.push({
      date: format(new Date(), 'MMM dd, yyyy'),
      price: position.currentPrice,
      type: 'current',
    })
  }

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="date"
          stroke="#64748b"
          style={{ fontSize: '12px' }}
        />
        <YAxis
          stroke="#64748b"
          style={{ fontSize: '12px' }}
          domain={['auto', 'auto']}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#141b2d',
            border: '1px solid #1e293b',
            borderRadius: '8px',
          }}
          formatter={(value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <ReferenceLine
          y={position.avgEntryPrice}
          stroke="#8b5cf6"
          strokeDasharray="3 3"
          label={{ value: 'Avg Entry', position: 'right', fill: '#8b5cf6' }}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="#00ff88"
          strokeWidth={2}
          dot={(props: any) => {
            const { cx, cy, payload } = props
            const color = payload.type === 'buy' ? '#00ff88' : payload.type === 'sell' ? '#ef4444' : '#3b82f6'
            return <circle cx={cx} cy={cy} r={4} fill={color} />
          }}
          name="Price"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

