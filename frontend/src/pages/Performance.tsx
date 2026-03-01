import { useState } from 'react'
import { useQuery } from '@apollo/client'
import { GET_PERFORMANCE, GET_PORTFOLIO_HISTORY, GET_DAILY_PNL_HISTORY } from '../graphql/queries'
import PortfolioValueChart from '../components/charts/PortfolioValueChart'
import DailyPnLChart from '../components/charts/DailyPnLChart'
import PnLCard from '../components/portfolio/PnLCard'

export default function Performance() {
  const [compareBtc, setCompareBtc] = useState(false)
  
  const { data: performanceData, loading: performanceLoading } = useQuery(GET_PERFORMANCE)
  const { data: historyData, loading: historyLoading } = useQuery(GET_PORTFOLIO_HISTORY, {
    variables: { days: 3650 }, // ~10 years for all-time
  })
  const { data: dailyPnLData, loading: dailyPnLLoading } = useQuery(GET_DAILY_PNL_HISTORY, {
    variables: { days: 30 },
  })

  if (performanceLoading || historyLoading || dailyPnLLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading performance data...</div>
      </div>
    )
  }

  const performance = performanceData?.performance
  const history = historyData?.portfolioHistory || []
  const dailyPnL = dailyPnLData?.dailyPnlHistory || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">Performance Analysis</h1>
      </div>

      {/* Performance Metrics */}
      <PnLCard
        value={performance?.totalValue || 0}
        pnl={performance?.todaysPnl || 0}
        pnlPercent={performance?.todaysPnlPercent || 0}
      />

      {/* Portfolio Value Evolution */}
      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Portfolio Value Evolution</h2>
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={compareBtc}
              onChange={(e) => setCompareBtc(e.target.checked)}
              className="w-4 h-4 rounded border-crypto-border bg-crypto-card text-crypto-green focus:ring-crypto-green"
            />
            <span className="text-sm text-gray-300">Compare with BTC</span>
          </label>
        </div>
        <PortfolioValueChart data={history} compareBtc={compareBtc} />
      </div>

      {/* Daily P&L Chart */}
      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
        <h2 className="text-xl font-semibold text-white mb-4">Daily P&L</h2>
        <DailyPnLChart data={dailyPnL} compareBtc={compareBtc} />
      </div>
    </div>
  )
}

