import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import ChartScrubOverlay from './ChartScrubOverlay'

export interface NavInspectPoint {
  timestamp: string
  totalValue: number
}

interface PortfolioValueChartProps {
  data: Array<{ timestamp: string; totalValue: number }>
  compareBtc?: boolean
  height?: number | string
  overlay?: React.ReactNode
  valueLabel?: string
  onPointInspect?: (point: NavInspectPoint | null) => void
}

export default function PortfolioValueChart({
  data,
  height = 250,
  overlay,
  onPointInspect,
}: PortfolioValueChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const onPointInspectRef = useRef(onPointInspect)
  onPointInspectRef.current = onPointInspect

  const chartData = useMemo(
    () =>
      data.map((item, index) => ({
        i: index,
        timestamp: item.timestamp,
        value: item.totalValue,
      })),
    [data],
  )

  const dataKey = `${data.length}:${data[0]?.timestamp ?? ''}:${data[data.length - 1]?.totalValue ?? ''}`

  useEffect(() => {
    setActiveIndex(null)
    onPointInspectRef.current?.(null)
  }, [dataKey])

  const handleIndex = useCallback(
    (index: number | null) => {
      setActiveIndex(index)
      if (index == null) {
        onPointInspect?.(null)
        return
      }
      const row = data[index]
      onPointInspect?.(row ? { timestamp: row.timestamp, totalValue: row.totalValue } : null)
    },
    [data, onPointInspect],
  )

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sillage-soft text-sm h-full" style={{ height }}>
        No history data
      </div>
    )
  }

  const activePoint = activeIndex != null ? chartData[activeIndex] : undefined

  return (
    <div className="relative h-full w-full chart-plot" style={{ height }}>
      {overlay}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--green)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="var(--green)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="i" type="number" domain={['dataMin', 'dataMax']} hide />
          <YAxis hide domain={['auto', 'auto']} />
          {activePoint != null && (
            <ReferenceLine
              x={activePoint.i}
              stroke="var(--soft)"
              strokeWidth={1}
              strokeOpacity={0.55}
              ifOverflow="extendDomain"
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--green)"
            strokeWidth={1.8}
            fill="url(#navFill)"
            dot={false}
            activeDot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <ChartScrubOverlay pointCount={chartData.length} onIndex={handleIndex} />
    </div>
  )
}
