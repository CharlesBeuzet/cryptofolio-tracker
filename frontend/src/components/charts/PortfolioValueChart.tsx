import { useMemo } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { format } from 'date-fns'

interface PortfolioValueChartProps {
  data: Array<{ timestamp: string; totalValue: number }>
  compareBtc?: boolean
  height?: number
  overlay?: React.ReactNode
}

export default function PortfolioValueChart({
  data,
  height = 250,
  overlay,
}: PortfolioValueChartProps) {
  const chartData = useMemo(
    () =>
      data.map((item) => ({
        date: format(new Date(item.timestamp), 'MMM dd'),
        value: item.totalValue,
      })),
    [data],
  )

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sillage-soft text-sm" style={{ height }}>
        No history data
      </div>
    )
  }

  return (
    <div className="relative" style={{ height }}>
      {overlay}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--green)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="var(--green)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--line)',
              borderRadius: '8px',
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: '11px',
            }}
            formatter={(value: number) => [
              `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
              'NAV',
            ]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--green)"
            strokeWidth={1.8}
            fill="url(#navFill)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
