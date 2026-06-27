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
