import { useQuery } from '@apollo/client'
import { Link } from 'react-router-dom'
import { GET_FIAT_DEPOSITS } from '../graphql/queries'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface FiatDepositRow {
  id: number
  depositedAt: string
  currency: string
  amount: number
  fee: number | null
  status: string | null
  exchange: string
  source: string
  externalOrderId: string | null
  method: string | null
  createdAt: string
}

interface ChartRow {
  id: number
  label: string
  amountNum: number
  depositedAt: string
  currency: string
  exchange: string
  source: string
}

export default function FiatDeposits() {
  const { data, loading, error } = useQuery(GET_FIAT_DEPOSITS, {
    variables: { limit: 500 },
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading fiat deposits...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-crypto-red text-center py-8">
        Failed to load fiat deposits: {error.message}
      </div>
    )
  }

  const rows: FiatDepositRow[] = data?.fiatDeposits ?? []

  const byCurrency: Record<string, ChartRow[]> = rows.reduce((acc, r: FiatDepositRow) => {
    const k = r.currency || 'UNK'
    const label = new Date(r.depositedAt).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: '2-digit',
    })
    const row: ChartRow = {
      id: r.id,
      label,
      amountNum: r.amount,
      depositedAt: r.depositedAt,
      currency: r.currency,
      exchange: r.exchange,
      source: r.source,
    }
    if (!acc[k]) acc[k] = []
    acc[k].push(row)
    return acc
  }, {} as Record<string, ChartRow[]>)

  for (const k of Object.keys(byCurrency)) {
    byCurrency[k].sort(
      (a: ChartRow, b: ChartRow) =>
        new Date(a.depositedAt).getTime() - new Date(b.depositedAt).getTime()
    )
  }

  const currencyCharts = Object.entries(byCurrency) as [string, ChartRow[]][]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-white">Fiat deposits</h1>
        <Link to="/" className="text-crypto-green hover:text-green-400 text-sm font-medium">
          ← Portfolio
        </Link>
      </div>

      <p className="text-gray-400 text-sm max-w-3xl">
        Recent Binance fiat deposit orders are pulled automatically on each portfolio sync. Older history or other
        exchanges can be added manually in SQLite (<code className="text-gray-300">fiat_deposits</code> table): use{' '}
        <code className="text-gray-300">source = &apos;manual&apos;</code> and set{' '}
        <code className="text-gray-300">external_order_id</code> to NULL unless you have a unique reference.
      </p>

      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6 space-y-8">
        <div>
          <h2 className="text-xl font-semibold text-white mb-1">Amount over time</h2>
          <p className="text-gray-500 text-sm mb-4">One chart per fiat currency so scales stay meaningful.</p>
        </div>
        {rows.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-500 text-sm">No records yet</div>
        ) : (
          currencyCharts.map(([currency, chartRows]) => (
            <div key={currency}>
              <h3 className="text-sm font-medium text-gray-400 mb-2">{currency}</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={chartRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#141b2d',
                      border: '1px solid #1e293b',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) =>
                      value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                    }
                    labelFormatter={(_, payload) => {
                      const p = payload?.[0]?.payload as ChartRow | undefined
                      if (!p) return ''
                      return `${p.exchange} · ${p.source}`
                    }}
                  />
                  <Bar dataKey="amountNum" fill="#00ff88" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ))
        )}
      </div>

      <div className="bg-crypto-card rounded-lg border border-crypto-border p-6 overflow-x-auto">
        <h2 className="text-xl font-semibold text-white mb-4">All records</h2>
        {rows.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No fiat deposit rows stored.</p>
        ) : (
          <table className="min-w-full divide-y divide-crypto-border">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Deposited
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Currency
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Amount
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Fee
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Exchange
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Source
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Order ref
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-crypto-border">
              {rows.map((r: {
                id: number
                depositedAt: string
                currency: string
                amount: number
                fee: number | null
                status: string | null
                exchange: string
                source: string
                externalOrderId: string | null
                method: string | null
              }) => (
                <tr key={r.id} className="hover:bg-crypto-border/40">
                  <td className="px-4 py-3 whitespace-nowrap text-gray-300 text-sm">
                    {new Date(r.depositedAt).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-white font-medium">{r.currency}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-right text-gray-200 tabular-nums">
                    {r.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-right text-gray-400 tabular-nums text-sm">
                    {r.fee != null
                      ? r.fee.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                      : '—'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-300 text-sm">{r.status ?? '—'}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-300 text-sm">{r.exchange}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-300 text-sm">{r.source}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-400 text-xs font-mono max-w-[140px] truncate" title={r.externalOrderId ?? ''}>
                    {r.externalOrderId ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
