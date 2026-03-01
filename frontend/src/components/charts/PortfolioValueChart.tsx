import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { format } from 'date-fns'

interface PortfolioValueChartProps {
  data: Array<{ timestamp: string; totalValue: number }>
  compareBtc?: boolean
}

export default function PortfolioValueChart({ data, compareBtc = false }: PortfolioValueChartProps) {
  // Format data for chart
  const chartData = data.map((item) => ({
    date: format(new Date(item.timestamp), 'MMM dd'),
    timestamp: item.timestamp,
    portfolio: item.totalValue,
    // TODO: Add BTC comparison data when API supports it
    btc: compareBtc ? item.totalValue * 0.95 : undefined, // Placeholder
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
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
          tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#141b2d',
            border: '1px solid #1e293b',
            borderRadius: '8px',
          }}
          formatter={(value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="portfolio"
          stroke="#00ff88"
          strokeWidth={2}
          dot={false}
          name="Portfolio"
        />
        {compareBtc && (
          <Line
            type="monotone"
            dataKey="btc"
            stroke="#f7931a"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            name="BTC"
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}

