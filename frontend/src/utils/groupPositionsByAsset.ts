/** Venue-level slice of an open position (one exchange / wallet). */
export interface PositionLike {
  id: number
  symbol: string
  quantity: number
  avgEntryPrice?: number | null
  value: number
  pnl?: number | null
  pnlPercent?: number | null
  exchange?: string | null
}

export interface AssetVenue {
  id: number
  exchange: string
  quantity: number
  value: number
  pnl: number
  pnlPercent: number
}

/** One overview row: all open venues for a single asset symbol. */
export interface GroupedAsset {
  symbol: string
  quantity: number
  value: number
  pnl: number
  /** Weighted unrealised % from consolidated cost basis (not an average of %). */
  pnlPercent: number
  /** Σ(avg entry × qty) across venues that have an entry price. */
  costBasis: number
  /** costBasis / quantity when both are positive. */
  avgEntryPrice: number
  venues: AssetVenue[]
  /** Largest venue by value — default drill-down target. */
  primaryId: number
}

/**
 * Roll up per-(symbol, exchange) positions into one row per asset.
 * Amount, value, and dollar PnL are summed; PnL % is cost-basis weighted.
 */
export function groupPositionsByAsset(positions: PositionLike[]): GroupedAsset[] {
  const bySymbol = new Map<
    string,
    {
      symbol: string
      quantity: number
      value: number
      pnl: number
      costBasis: number
      venues: AssetVenue[]
    }
  >()

  for (const p of positions) {
    const symbol = (p.symbol || '').toUpperCase()
    if (!symbol) continue

    const quantity = p.quantity || 0
    const value = p.value || 0
    const pnl = p.pnl || 0
    const avgEntry = p.avgEntryPrice || 0
    const exchange = (p.exchange || '—').trim() || '—'

    let group = bySymbol.get(symbol)
    if (!group) {
      group = { symbol, quantity: 0, value: 0, pnl: 0, costBasis: 0, venues: [] }
      bySymbol.set(symbol, group)
    }

    group.quantity += quantity
    group.value += value
    group.pnl += pnl
    if (avgEntry > 0 && quantity > 0) {
      group.costBasis += avgEntry * quantity
    }
    group.venues.push({
      id: p.id,
      exchange,
      quantity,
      value,
      pnl,
      pnlPercent: p.pnlPercent || 0,
    })
  }

  return Array.from(bySymbol.values())
    .map((g) => {
      const venues = [...g.venues].sort((a, b) => b.value - a.value)
      const primary = venues[0]
      return {
        symbol: g.symbol,
        quantity: g.quantity,
        value: g.value,
        pnl: g.pnl,
        pnlPercent: g.costBasis > 0 ? (g.pnl / g.costBasis) * 100 : 0,
        costBasis: g.costBasis,
        avgEntryPrice: g.quantity > 0 && g.costBasis > 0 ? g.costBasis / g.quantity : 0,
        venues,
        primaryId: primary?.id ?? 0,
      }
    })
    .sort((a, b) => b.value - a.value)
}
