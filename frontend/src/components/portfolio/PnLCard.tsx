interface PnLCardProps {
  value: number
  pnl: number
  pnlPercent: number
}

export default function PnLCard({ value, pnl, pnlPercent }: PnLCardProps) {
  const isPositive = pnl >= 0

  return (
    <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400 mb-1">Total Portfolio Value</p>
          <p className="text-3xl font-bold text-white">
            ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-400 mb-1">Today's P&L</p>
          <p className={`text-2xl font-bold ${isPositive ? 'text-crypto-green' : 'text-crypto-red'}`}>
            {isPositive ? '+' : ''}${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className={`text-sm ${isPositive ? 'text-crypto-green' : 'text-crypto-red'}`}>
            {isPositive ? '+' : ''}{pnlPercent.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  )
}

