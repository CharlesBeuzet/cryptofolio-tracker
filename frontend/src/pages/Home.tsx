import { useQuery } from '@apollo/client'
import { Link } from 'react-router-dom'
import { GET_PORTFOLIO, GET_PORTFOLIO_HISTORY, GET_FIAT_DEPOSITS_SUMMARY } from '../graphql/queries'
import PortfolioValueChart from '../components/charts/PortfolioValueChart'
import PieChart from '../components/charts/PieChart'
import PnLCard from '../components/portfolio/PnLCard'
import PositionsList from '../components/portfolio/PositionsList'
import FiatSummaryCard from '../components/portfolio/FiatSummaryCard'

export default function Home() {
  const { data: portfolioData, loading: portfolioLoading } = useQuery(GET_PORTFOLIO)
  const { data: historyData, loading: historyLoading } = useQuery(GET_PORTFOLIO_HISTORY, {
    variables: { days: 180 },
  })
  const { data: fiatSummaryData, loading: fiatSummaryLoading } = useQuery(GET_FIAT_DEPOSITS_SUMMARY)

  if (portfolioLoading || historyLoading || fiatSummaryLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading portfolio data...</div>
      </div>
    )
  }

  const portfolio = portfolioData?.portfolio
  const history = historyData?.portfolioHistory || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">Portfolio Overview</h1>
        <Link
          to="/performance"
          className="text-crypto-green hover:text-green-400 text-sm font-medium"
        >
          View Performance →
        </Link>
      </div>

      {/* Today's P&L Card */}
      <PnLCard
        value={portfolio?.totalValue || 0}
        pnl={portfolio?.todaysPnl || 0}
        pnlPercent={portfolio?.todaysPnlPercent || 0}
      />

      <FiatSummaryCard
        totalsByCurrency={fiatSummaryData?.fiatDepositsSummary?.totalsByCurrency || []}
        includedRecordCount={fiatSummaryData?.fiatDepositsSummary?.includedRecordCount ?? 0}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Portfolio Value Graph */}
        <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-white">Portfolio Value (6M)</h2>
            <Link
              to="/performance"
              className="text-crypto-green hover:text-green-400 text-sm"
            >
              More →
            </Link>
          </div>
          <PortfolioValueChart data={history} />
        </div>

        {/* Pie Chart */}
        <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
          <h2 className="text-xl font-semibold text-white mb-4">Asset Distribution</h2>
          <PieChart positions={portfolio?.positions || []} />
        </div>
      </div>

      {/* Positions List */}
      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6">
        <h2 className="text-xl font-semibold text-white mb-4">Positions</h2>
        <PositionsList positions={portfolio?.positions || []} />
      </div>
    </div>
  )
}

