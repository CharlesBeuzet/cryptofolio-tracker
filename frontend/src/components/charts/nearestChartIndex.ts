export interface PlotBounds {
  left: number
  width: number
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Map a pointer X to 0–1 across the plot (or the full container if bounds are missing). */
export function ratioFromClientX(
  clientX: number,
  containerRect: DOMRect,
  plotBounds?: PlotBounds | null,
): number {
  const left = containerRect.left + (plotBounds?.left ?? 0)
  const width = plotBounds?.width ?? containerRect.width
  if (!(width > 0)) return 0
  return clamp((clientX - left) / width, 0, 1)
}

/** Evenly spaced category axis: ratio 0 is the first point, 1 is the last. */
export function indexFromRatio(count: number, ratio: number): number {
  if (count <= 1) return 0
  return Math.round(clamp(ratio, 0, 1) * (count - 1))
}

/**
 * Numeric time axis spanning [first, last] timestamp.
 * `timestamps` must be sorted ascending.
 */
export function nearestTimeIndex(timestamps: number[], ratio: number): number {
  const n = timestamps.length
  if (n === 0) return 0
  if (n === 1) return 0

  const tMin = timestamps[0]
  const tMax = timestamps[n - 1]
  if (tMax === tMin) return 0

  const target = tMin + clamp(ratio, 0, 1) * (tMax - tMin)

  let lo = 0
  let hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (timestamps[mid] < target) lo = mid + 1
    else hi = mid
  }

  if (lo === 0) return 0
  const prev = lo - 1
  return Math.abs(timestamps[prev] - target) <= Math.abs(timestamps[lo] - target) ? prev : lo
}
