export interface NavPoint {
  timestamp: string
  totalValue: number
}

/**
 * Append the live portfolio NAV as the final chart point so the curve
 * endpoint matches the homepage overlay (which uses live totalValue).
 *
 * Historical points stay as stored snapshots; only the tip is "now".
 */
export function appendLiveNavPoint(
  history: NavPoint[],
  liveTotalValue: number,
  now: Date = new Date(),
): NavPoint[] {
  if (!Number.isFinite(liveTotalValue)) {
    return history
  }

  const livePoint: NavPoint = {
    timestamp: now.toISOString(),
    totalValue: liveTotalValue,
  }

  if (history.length === 0) {
    return [livePoint]
  }

  const lastTs = new Date(history[history.length - 1].timestamp).getTime()
  const nowTs = now.getTime()

  // Avoid a backward time step if the latest snapshot is at/after "now".
  if (!Number.isNaN(lastTs) && lastTs >= nowTs) {
    return [...history.slice(0, -1), livePoint]
  }

  return [...history, livePoint]
}
