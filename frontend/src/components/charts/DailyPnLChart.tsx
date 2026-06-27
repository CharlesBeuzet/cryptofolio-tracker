import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { format, parseISO } from 'date-fns'

interface DailyPnLChartProps {
  data: Array<{ date: string; pnl: number; pnlPercent: number }>
  compareBtc?: boolean
}

export default function DailyPnLChart({ data }: DailyPnLChartProps) {
  const chartData = data.map((item) => ({
    date: format(parseISO(item.date), 'MMM dd'),
    pnl: item.pnl,
  }))

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm">
        No daily P&amp;L data
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData}>
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
          tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
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
        <Bar dataKey="pnl" fill="var(--green)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
