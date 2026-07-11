import { format } from 'date-fns'

const SUCCESS_STATUSES = new Set(['successful', 'completed', 'complete', 'success'])

/** Mirrors backend fiat summary inclusion rules. */
export function depositCountsInTotal(
  amount: number,
  status: string | null,
  source: string,
): number {
  if (source === 'manual') return amount
  if (!status) return 0
  if (SUCCESS_STATUSES.has(status.toLowerCase())) return amount
  return 0
}

export interface OnRampChartPoint {
  ts: number
  date: string
  nav: number
  deposits: number
}

interface NavSnapshot {
  timestamp: string
  totalValue: number
}

interface FiatDepositInput {
  depositedAt: string
  amount: number
  status: string | null
  source: string
}

/**
 * Build a merged timeline for the on-ramp chart.
 * Both series start at 0 one day before the first real event; each line only
 * changes on its own events (step behaviour via forward-filled values).
 */
export function buildOnRampChartData(
  navHistory: NavSnapshot[],
  deposits: FiatDepositInput[],
): OnRampChartPoint[] {
  const bucket = new Map<number, { nav?: number; depositDelta?: number }>()

  for (const h of navHistory) {
    const ts = new Date(h.timestamp).getTime()
    if (Number.isNaN(ts)) continue
    const cur = bucket.get(ts) ?? {}
    cur.nav = h.totalValue
    bucket.set(ts, cur)
  }

  for (const d of deposits) {
    const delta = depositCountsInTotal(d.amount, d.status, d.source)
    if (delta <= 0) continue
    const ts = new Date(d.depositedAt).getTime()
    if (Number.isNaN(ts)) continue
    const cur = bucket.get(ts) ?? {}
    cur.depositDelta = (cur.depositDelta ?? 0) + delta
    bucket.set(ts, cur)
  }

  const timestamps = [...bucket.keys()].sort((a, b) => a - b)
  if (timestamps.length === 0) return []

  const originTs = timestamps[0] - 86_400_000
  const points: OnRampChartPoint[] = [
    { ts: originTs, date: format(new Date(originTs), 'MMM dd, yy'), nav: 0, deposits: 0 },
  ]

  let cumDeposits = 0
  let lastNav = 0

  for (const ts of timestamps) {
    const evt = bucket.get(ts)!
    if (evt.depositDelta) cumDeposits += evt.depositDelta
    if (evt.nav !== undefined) lastNav = evt.nav
    points.push({
      ts,
      date: format(new Date(ts), 'MMM dd, yy'),
      nav: lastNav,
      deposits: cumDeposits,
    })
  }

  return points
}
