const SUBSCRIPT_DIGITS = '₀₁₂₃₄₅₆₇₈₉'

/** Significant digits shown after the first non-zero decimal for sub-$1 prices. */
const TOKEN_PRICE_SIG_DIGITS = 4

/** Use compact 0.0ₙ… notation when this many leading zeros follow the decimal point. */
const COMPACT_ZERO_THRESHOLD = 3

function toSubscript(count: number): string {
  return String(count)
    .split('')
    .map((digit) => SUBSCRIPT_DIGITS[Number(digit)])
    .join('')
}

/**
 * Format a per-token USD price with adaptive precision.
 * - ≥ $1 → two decimals ($X.XX)
 * - $0.01–$1 → up to six decimals, enough for analysis
 * - < $0.01 with many leading zeros → compact notation ($0.0₄1234)
 */
export function formatTokenPrice(value: number): string {
  if (!Number.isFinite(value)) return '$—'
  if (value === 0) return '$0.00'

  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)

  if (abs >= 1) {
    return `${sign}$${abs.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  }

  if (abs >= 0.01) {
    return `${sign}$${abs.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    })}`
  }

  const match = abs.toFixed(18).match(/^0\.(0*)([1-9]\d*)/)
  if (!match) {
    return `${sign}$${abs.toPrecision(TOKEN_PRICE_SIG_DIGITS)}`
  }

  const [, zeroRun, tail] = match
  const zeroCount = zeroRun.length
  const digits = tail.slice(0, TOKEN_PRICE_SIG_DIGITS)

  if (zeroCount < COMPACT_ZERO_THRESHOLD) {
    const decimals = zeroCount + TOKEN_PRICE_SIG_DIGITS
    return `${sign}$${abs.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}`
  }

  return `${sign}$0.0${toSubscript(zeroCount)}${digits}`
}

export function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

export function formatUsdPrecise(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatPct(value: number, signed = true): string {
  const prefix = signed && value >= 0 ? '+' : ''
  return `${prefix}${value.toFixed(1)}%`
}

export const ASSET_COLORS = [
  '#4FBE86',
  '#E0A35E',
  '#6B9FD4',
  '#C47EB5',
  '#D98A6A',
  '#8BA888',
  '#A8C4E0',
  '#B8A67A',
]

export function assetColor(index: number): string {
  return ASSET_COLORS[index % ASSET_COLORS.length]
}

export function pnlColorClass(value: number): string {
  return value >= 0 ? 'text-sillage-green' : 'text-sillage-down'
}
