const RANGES = ['24h', '7d', '30d', '90d', '1Y'] as const
export type RangeKey = (typeof RANGES)[number]

const RANGE_DAYS: Record<RangeKey, number> = {
  '24h': 1,
  '7d': 7,
  '30d': 30,
  '90d': 90,
  '1Y': 365,
}

const RANGE_LABELS: Record<RangeKey, string> = {
  '24h': 'trailing 24h',
  '7d': 'trailing 7d',
  '30d': 'trailing 30d',
  '90d': 'trailing 90d',
  '1Y': 'trailing 1Y',
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
