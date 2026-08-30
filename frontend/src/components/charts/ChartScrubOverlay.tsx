import type { PlotBounds } from './nearestChartIndex'
import { useChartScrub } from './useChartScrub'

interface ChartScrubOverlayProps {
  pointCount: number
  onIndex: (index: number | null) => void
  plotBounds?: PlotBounds | null
  getIndex?: (ratio: number) => number
}

/** Transparent hit layer on top of a Recharts plot. */
export default function ChartScrubOverlay({
  pointCount,
  onIndex,
  plotBounds,
  getIndex,
}: ChartScrubOverlayProps) {
  const { ref, ...handlers } = useChartScrub({ pointCount, onIndex, plotBounds, getIndex })

  if (pointCount <= 0) return null

  return <div ref={ref} className="absolute inset-0 z-[1] chart-plot" {...handlers} />
}
