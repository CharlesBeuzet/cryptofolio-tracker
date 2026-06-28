import { Link } from 'react-router-dom'

interface CurrencyTotal {
  currency: string
  totalAmount: number
}

interface FiatSummaryCardProps {
  totalsByCurrency: CurrencyTotal[]
  includedRecordCount: number
}

export default function FiatSummaryCard({ totalsByCurrency, includedRecordCount }: FiatSummaryCardProps) {
  const hasTotals = totalsByCurrency.length > 0

  return (
    <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-white">Fiat injected</h2>
        <Link to="/fiat-deposits" className="text-crypto-green hover:text-green-400 text-sm font-medium">
          Details →
        </Link>
      </div>
      <p className="text-sm text-gray-400 mb-4">
        Totals by currency (successful Binance fiat deposits plus any manual rows). Amounts are in the original fiat
        unit, not converted to USD.
      </p>
      {!hasTotals ? (
        <p className="text-gray-500 text-sm">No qualifying deposit records yet. Sync runs with scheduled portfolio updates.</p>
      ) : (
        <ul className="space-y-2">
          {totalsByCurrency.map((row) => (
            <li key={row.currency} className="flex justify-between items-baseline text-gray-200">
              <span className="font-medium">{row.currency}</span>
              <span className="tabular-nums">
                {row.totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-gray-500 mt-4">
        {includedRecordCount} record{includedRecordCount === 1 ? '' : 's'} included in totals
      </p>
    </div>
  )
}
