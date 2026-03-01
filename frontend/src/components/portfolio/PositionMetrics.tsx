import { format } from 'date-fns'

interface Position {
  symbol: string
  quantity: number
  value: number
  avgEntryPrice: number
  currentPrice: number | null
  pnl: number | null
  pnlPercent: number | null
  firstBoughtAt: string
  durationDays: number
}

interface PositionMetricsProps {
  position: Position
}

export default function PositionMetrics({ position }: PositionMetricsProps) {
  const isPositive = (position.pnl || 0) >= 0

  return (
    <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
      <h2 className="text-xl font-semibold text-white mb-4">Position Details</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-sm text-gray-400 mb-1">Value</p>
          <p className="text-lg font-semibold text-white">
            ${position.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">Quantity</p>
          <p className="text-lg font-semibold text-white">
            {position.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">Current P&L</p>
          <p className={`text-lg font-semibold ${isPositive ? 'text-crypto-green' : 'text-crypto-red'}`}>
            {isPositive ? '+' : ''}${(position.pnl || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className={`text-sm ${isPositive ? 'text-crypto-green' : 'text-crypto-red'}`}>
            {isPositive ? '+' : ''}{(position.pnlPercent || 0).toFixed(2)}%
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">Duration</p>
          <p className="text-lg font-semibold text-white">
            {position.durationDays} days
          </p>
          <p className="text-xs text-gray-500">
            Since {format(new Date(position.firstBoughtAt), 'MMM dd, yyyy')}
          </p>
        </div>
      </div>
    </div>
  )
}

