import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { format, parseISO } from 'date-fns'

interface DailyPnLChartProps {
  data: Array<{ date: string; pnl: number; pnlPercent: number }>
  compareBtc?: boolean
}

export default function DailyPnLChart({ data, compareBtc = false }: DailyPnLChartProps) {
  const chartData = data.map((item) => ({
    date: format(parseISO(item.date), 'MMM dd'),
    pnl: item.pnl,
    pnlPercent: item.pnlPercent,
    // TODO: Add BTC comparison when API supports it
    btcPnl: compareBtc ? item.pnl * 0.9 : undefined,
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData}>
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
        <Bar
          dataKey="pnl"
          fill="#00ff88"
          name="Portfolio P&L"
          radius={[4, 4, 0, 0]}
        />
        {compareBtc && (
          <Bar
            dataKey="btcPnl"
            fill="#f7931a"
            name="BTC P&L"
            radius={[4, 4, 0, 0]}
          />
        )}
      </BarChart>
    </ResponsiveContainer>
  )
}

