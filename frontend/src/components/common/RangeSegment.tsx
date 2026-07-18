const RANGES = ['24h', '7d', '30d', '90d', '1Y', '2Y', 'Max'] as const
export type RangeKey = (typeof RANGES)[number]

/** Sentinel for Max: backend interprets 0 as all available history. */
export const MAX_RANGE_DAYS = 0

const RANGE_DAYS: Record<RangeKey, number> = {
  '24h': 1,
  '7d': 7,
  '30d': 30,
  '90d': 90,
  '1Y': 365,
  '2Y': 730,
  Max: MAX_RANGE_DAYS,
}

const RANGE_LABELS: Record<RangeKey, string> = {
  '24h': 'trailing 24h',
  '7d': 'trailing 7d',
  '30d': 'trailing 30d',
  '90d': 'trailing 90d',
  '1Y': 'trailing 1Y',
  '2Y': 'trailing 2Y',
  Max: 'all available',
}

interface RangeSegmentProps {
  value: RangeKey
  onChange: (range: RangeKey) => void
}

export function rangeToDays(range: RangeKey): number {
  return RANGE_DAYS[range]
}

export function rangeLabel(range: RangeKey): string {
  return RANGE_LABELS[range]
}

export default function RangeSegment({ value, onChange }: RangeSegmentProps) {
  return (
    <div className="seg">
      {RANGES.map((r) => (
        <button
          key={r}
          type="button"
          className={`segb ${value === r ? 'on' : ''}`}
          onClick={() => onChange(r)}
        >
          {r}
        </button>
      ))}
    </div>
  )
}
