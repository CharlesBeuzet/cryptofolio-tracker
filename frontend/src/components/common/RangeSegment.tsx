import { useEffect, useRef } from 'react'

const RANGES = ['24h', '7d', '30d', '90d', '1Y', '2Y', '5Y'] as const
export type RangeKey = (typeof RANGES)[number]

const RANGE_DAYS: Record<RangeKey, number> = {
  '24h': 1,
  '7d': 7,
  '30d': 30,
  '90d': 90,
  '1Y': 365,
  '2Y': 730,
  '5Y': 1825,
}

const RANGE_LABELS: Record<RangeKey, string> = {
  '24h': 'trailing 24h',
  '7d': 'trailing 7d',
  '30d': 'trailing 30d',
  '90d': 'trailing 90d',
  '1Y': 'trailing 1Y',
  '2Y': 'trailing 2Y',
  '5Y': 'trailing 5Y',
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
  const scrollerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scroller = scrollerRef.current
    if (!scroller) return
    const selected = scroller.querySelector<HTMLElement>('[aria-pressed="true"]')
    if (!selected) return

    const scrollerBox = scroller.getBoundingClientRect()
    const selectedBox = selected.getBoundingClientRect()
    const fullyVisible =
      selectedBox.left >= scrollerBox.left && selectedBox.right <= scrollerBox.right
    if (fullyVisible) return

    const nextLeft =
      scroller.scrollLeft + (selectedBox.left - scrollerBox.left) - (scrollerBox.width - selectedBox.width) / 2
    scroller.scrollTo({ left: Math.max(0, nextLeft), behavior: 'smooth' })
  }, [value])

  return (
    <div ref={scrollerRef} className="seg-scroll" role="group" aria-label="Time range">
      <div className="seg">
        {RANGES.map((r) => (
          <button
            key={r}
            type="button"
            className={`segb ${value === r ? 'on' : ''}`}
            onClick={() => onChange(r)}
            aria-pressed={value === r}
          >
            {r}
          </button>
        ))}
      </div>
    </div>
  )
}
