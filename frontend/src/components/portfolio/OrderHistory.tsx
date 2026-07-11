import { format } from 'date-fns'
import { formatTokenPrice } from '../../utils/format'

interface Order {
  id: number
  symbol: string
  type: string
  quantity: number
  price: number
  executedAt: string
  exchange: string | null
}

interface OrderHistoryProps {
  orders: Order[]
}

export default function OrderHistory({ orders }: OrderHistoryProps) {
  // Sort orders by execution time (newest first)
  const sortedOrders = [...orders].sort(
    (a, b) => new Date(b.executedAt).getTime() - new Date(a.executedAt).getTime()
  )

  if (sortedOrders.length === 0) {
    return (
      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
        <h2 className="text-xl font-semibold text-white mb-4">Order History</h2>
        <div className="text-center py-8 text-gray-400">
          No orders found
        </div>
      </div>
    )
  }

  return (
    <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
      <h2 className="text-xl font-semibold text-white mb-4">Order History</h2>
      <div className="space-y-3 max-h-[600px] overflow-y-auto">
        {sortedOrders.map((order) => {
          const isBuy = order.type === 'buy'
          const totalValue = order.quantity * order.price

          return (
            <div
              key={order.id}
              className="border-b border-crypto-border pb-3 last:border-0"
            >
              <div className="flex items-center justify-between mb-1">
                <span
                  className={`text-sm font-medium ${
                    isBuy ? 'text-crypto-green' : 'text-crypto-red'
                  }`}
                >
                  {isBuy ? 'BUY' : 'SELL'}
                </span>
                <span className="text-xs text-gray-400">
                  {format(new Date(order.executedAt), 'MMM dd, HH:mm')}
                </span>
              </div>
              <div className="text-sm text-gray-300">
                <div>Qty: {order.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                <div>Price: {formatTokenPrice(order.price)}</div>
                <div className="text-white font-medium">
                  Total: ${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
              {order.exchange && (
                <div className="text-xs text-gray-500 mt-1">
                  {order.exchange}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

