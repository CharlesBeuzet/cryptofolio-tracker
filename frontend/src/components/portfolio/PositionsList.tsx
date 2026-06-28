import { Link } from 'react-router-dom'

interface Position {
  id: number
  symbol: string
  quantity: number
  value: number
  pnl: number | null
  pnlPercent: number | null
  currentPrice: number | null
}

interface PositionsListProps {
  positions: Position[]
}

export default function PositionsList({ positions }: PositionsListProps) {
  // Sort by portfolio share (value)
  const sortedPositions = [...positions].sort((a, b) => b.value - a.value)
  const totalValue = positions.reduce((sum, pos) => sum + pos.value, 0)

  if (sortedPositions.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        No positions found
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-crypto-border">
        <thead>
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              Symbol
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              Quantity
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              Price
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              Value
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              Share
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
              P&L
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-crypto-border">
          {sortedPositions.map((position) => {
            const share = totalValue > 0 ? (position.value / totalValue * 100) : 0
            const isPositive = (position.pnl || 0) >= 0

            return (
              <tr
                key={position.id}
                className="hover:bg-crypto-border cursor-pointer transition-colors"
              >
                <td className="px-6 py-4 whitespace-nowrap">
                  <Link
                    to={`/position/${position.id}`}
                    className="text-white font-medium hover:text-crypto-green"
                  >
                    {position.symbol}
                  </Link>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-gray-300">
                  {position.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-gray-300">
                  {position.currentPrice
                    ? `$${position.currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : 'N/A'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-white font-medium">
                  ${position.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-gray-300">
                  {share.toFixed(1)}%
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={isPositive ? 'text-crypto-green' : 'text-crypto-red'}>
                    {isPositive ? '+' : ''}${(position.pnl || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <br />
                  <span className={`text-sm ${isPositive ? 'text-crypto-green' : 'text-crypto-red'}`}>
                    {isPositive ? '+' : ''}{(position.pnlPercent || 0).toFixed(2)}%
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

