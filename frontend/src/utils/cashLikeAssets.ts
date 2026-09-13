/** USD-pegged stables commonly listed as exchange balances. */
const USD_STABLES = [
  'USDT',
  'USDC',
  'BUSD',
  'DAI',
  'TUSD',
  'FDUSD',
  'USDP',
  'PYUSD',
  'USDE',
  'USDD',
  'FRAX',
  'LUSD',
  'GUSD',
  'RLUSD',
  'USDS',
  'USD1',
] as const

/** EUR-pegged stables, including EURON. */
const EUR_STABLES = ['EURON', 'EURC', 'EUROC', 'EURS', 'EURT', 'AEUR', 'EURI'] as const

/**
 * Fiat buckets that CEX balance APIs may return as positions.
 * Deliberately not a full ISO 4217 list — tickers like RON / MNT / GEL collide with crypto.
 */
const CEX_FIAT = [
  'USD',
  'EUR',
  'GBP',
  'CHF',
  'JPY',
  'CAD',
  'AUD',
  'SGD',
  'HKD',
  'KRW',
  'CNY',
  'INR',
  'BRL',
  'MXN',
  'TRY',
  'PLN',
  'SEK',
  'NOK',
  'DKK',
  'NZD',
  'AED',
  'SAR',
  'TWD',
  'THB',
] as const

const CASH_LIKE_SYMBOLS = new Set<string>([...USD_STABLES, ...EUR_STABLES, ...CEX_FIAT])

/** True for stablecoins and fiat balances — no orders / P&L to inspect. */
export function isCashLikeAsset(symbol: string | null | undefined): boolean {
  if (!symbol) return false
  return CASH_LIKE_SYMBOLS.has(symbol.trim().toUpperCase())
}

export function excludeCashLikePositions<T>(positions: T[]): T[] {
  return positions.filter((p) => !isCashLikeAsset((p as { symbol?: string | null }).symbol))
}
