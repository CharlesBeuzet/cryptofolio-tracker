import { useMemo } from 'react'
import { assetColor } from '../../utils/format'
import { groupPositionsByAsset, type PositionLike } from '../../utils/groupPositionsByAsset'

interface AllocationSlice {
  symbol: string
  value: number
}

interface AllocationDonutProps {
  /** Raw venue positions (grouped by symbol) or already-aggregated asset slices. */
  positions: Array<PositionLike | AllocationSlice>
}

export default function AllocationDonut({ positions }: AllocationDonutProps) {
  const assets = useMemo(() => {
    const first = positions[0]
    // Venue rows from GraphQL carry a numeric position id; asset rollups do not.
    if (first && 'id' in first && typeof first.id === 'number') {
      return groupPositionsByAsset(positions as PositionLike[])
        .filter((a) => a.value > 0)
        .map((a) => ({ symbol: a.symbol, value: a.value }))
    }

    return [...positions]
      .filter((p) => p.value > 0)
      .map((p) => ({ symbol: p.symbol, value: p.value }))
      .sort((a, b) => b.value - a.value)
  }, [positions])

  const totalValue = assets.reduce((sum, p) => sum + p.value, 0)

  const segments = useMemo(() => {
    let acc = 0
    return assets.map((pos, i) => {
      const pct = totalValue > 0 ? (pos.value / totalValue) * 100 : 0
      const start = acc
      acc += pct
      return { ...pos, color: assetColor(i), pct, start, end: acc }
    })
  }, [assets, totalValue])

  const donutBg =
    segments.length > 0
      ? `conic-gradient(${segments.map((s) => `${s.color} ${s.start.toFixed(2)}% ${s.end.toFixed(2)}%`).join(', ')})`
      : 'var(--line)'

  if (assets.length === 0) {
    return <div className="flex items-center justify-center h-48 text-sillage-soft text-sm">No positions</div>
  }

  return (
    <>
      <div className="relative flex items-center justify-center">
        <div className="w-[148px] h-[148px] rounded-full" style={{ background: donutBg }} />
        <div className="absolute inset-[22px] rounded-full flex flex-col items-center justify-center bg-sillage-card">
          <div className="font-mono font-semibold text-xl">{assets.length}</div>
          <div className="lbl text-[9px]">assets</div>
        </div>
      </div>
      <div className="mt-5 w-full flex flex-col gap-2">
        {segments.map((s) => (
          <div key={s.symbol} className="flex items-center gap-2 text-xs">
            <span className="sw" style={{ background: s.color }} />
            <span className="tk text-xs flex-1">{s.symbol}</span>
            <span className="font-mono text-sillage-soft tabular-nums text-[11px]">{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </>
  )
}
