import { useParams } from 'react-router-dom'
import { useQuery } from '@apollo/client'
import { GET_POSITION } from '../graphql/queries'
import PositionChart from '../components/charts/PositionChart'
import PositionMetrics from '../components/portfolio/PositionMetrics'
import OrderHistory from '../components/portfolio/OrderHistory'

export default function Position() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, error } = useQuery(GET_POSITION, {
    variables: { id: parseInt(id || '0') },
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading position data...</div>
      </div>
    )
  }

  if (error || !data?.position) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-400">Error loading position data</div>
      </div>
    )
  }

  const position = data.position

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">{position.symbol} Position</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Order History Sidebar */}
        <div className="lg:col-span-1">
          <OrderHistory orders={position.orders || []} />
        </div>

        {/* Main Chart and Metrics */}
        <div className="lg:col-span-3 space-y-6">
          {/* Position Metrics */}
          <PositionMetrics position={position} />

          {/* Price Chart */}
          <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
            <h2 className="text-xl font-semibold text-white mb-4">Price Evolution</h2>
            <PositionChart position={position} />
          </div>
        </div>
      </div>
    </div>
  )
}

