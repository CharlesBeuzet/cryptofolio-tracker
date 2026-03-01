import { PieChart as RechartsPieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'

interface Position {
  symbol: string
  value: number
}

interface PieChartProps {
  positions: Position[]
}

const COLORS = [
  '#00ff88',
  '#3b82f6',
  '#8b5cf6',
  '#f59e0b',
  '#ef4444',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
]

export default function PieChart({ positions }: PieChartProps) {
  const totalValue = positions.reduce((sum, pos) => sum + (pos.value || 0), 0)
  
  const chartData = positions
    .map((pos) => ({
      name: pos.symbol,
      value: pos.value || 0,
      percentage: totalValue > 0 ? ((pos.value || 0) / totalValue * 100).toFixed(1) : '0',
    }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        No positions to display
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RechartsPieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={({ name, percentage }) => `${name} ${percentage}%`}
          outerRadius={100}
          fill="#8884d8"
          dataKey="value"
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: '#141b2d',
            border: '1px solid #1e293b',
            borderRadius: '8px',
          }}
          formatter={(value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <Legend />
      </RechartsPieChart>
    </ResponsiveContainer>
  )
}

