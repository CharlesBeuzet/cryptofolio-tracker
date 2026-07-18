import { useQuery } from '@apollo/client'
import { useMemo } from 'react'
import { ComposedChart, Line, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { GET_FIAT_DEPOSITS, GET_FIAT_DEPOSITS_SUMMARY, GET_PORTFOLIO_HISTORY } from '../graphql/queries'
import { formatUsd, formatUsdPrecise } from '../utils/format'
import { buildOnRampChartData } from '../utils/onRampChart'
import { format } from 'date-fns'

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
}

export default function FiatDeposits() {
  const { data, loading, error } = useQuery(GET_FIAT_DEPOSITS, { variables: { limit: 500 } })
  const { data: summaryData } = useQuery(GET_FIAT_DEPOSITS_SUMMARY)
  const { data: historyData } = useQuery(GET_PORTFOLIO_HISTORY, { variables: { days: 365 } })

  const rows: FiatDepositRow[] = data?.fiatDeposits ?? []
  const sorted = useMemo(
    () => [...rows].sort((a, b) => new Date(a.depositedAt).getTime() - new Date(b.depositedAt).getTime()),
    [rows],
  )

  const chartData = useMemo(
    () => buildOnRampChartData(historyData?.portfolioHistory || [], sorted),
    [historyData, sorted],
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sillage-soft font-mono text-sm">Loading fiat deposits…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-sillage-down text-center py-8 font-mono text-sm">
        Failed to load fiat deposits: {error.message}
      </div>
    )
  }

  const totalOnRamped = (summaryData?.fiatDepositsSummary?.totalsByCurrency || []).reduce(
    (s: number, r: { totalAmount: number }) => s + r.totalAmount,
    0,
  )
  const depositCount = summaryData?.fiatDepositsSummary?.includedRecordCount ?? rows.length
  const avgDeposit = depositCount > 0 ? totalOnRamped / depositCount : 0
  const firstDeposit = sorted[0]
  const navHistory = historyData?.portfolioHistory || []
  const latestNav = navHistory.length > 0 ? navHistory[navHistory.length - 1].totalValue : 0
  const netMultiple = totalOnRamped > 0 ? latestNav / totalOnRamped : 0

  let cumulative = 0
  const ledger = sorted.map((r) => {
    cumulative += r.amount
    return {
      ...r,
      cumulative,
      label: format(new Date(r.depositedAt), 'MMM dd, yy'),
      methodLabel: [r.method, r.exchange].filter(Boolean).join(' · ') || r.exchange,
    }
  })

  return (
    <div>
      <div className="mb-[18px]">
        <div className="lbl">§3 · On-ramp</div>
        <div className="font-serif text-[26px] leading-none mt-[7px]">Capital deployed from fiat</div>
      </div>

      <div className="flex gap-5 items-stretch flex-col lg:flex-row">
        <div className="panel flex-1 min-w-0">
          <div className="lbl mb-3">Fig 3 · Cumulative on-ramp vs net asset value</div>
          {chartData.length === 0 ? (
            <div className="h-[220px] flex items-center justify-center text-sillage-soft text-sm">
              No chart data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--card)',
                    border: '1px solid var(--line)',
                    borderRadius: '8px',
                    fontFamily: 'IBM Plex Mono, monospace',
                    fontSize: '11px',
                  }}
                  formatter={(value: number, name: string) => [
                    formatUsd(value),
                    name === 'nav' ? 'Net asset value' : 'Cumulative on-ramp',
                  ]}
                  labelFormatter={(label) => String(label)}
                />
                <Line
                  type="monotone"
                  dataKey="nav"
                  stroke="var(--green)"
                  strokeWidth={1.8}
                  dot={false}
                />
                <Line
                  type="stepAfter"
                  dataKey="deposits"
                  stroke="var(--accent)"
                  strokeWidth={1.6}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
          <div className="font-mono text-[11px] flex gap-[18px] mt-3">
            <span>
              <span className="text-sillage-green">━</span> net asset value
            </span>
            <span>
              <span className="text-sillage-accent">╌</span> cumulative on-ramp
            </span>
          </div>
        </div>

        <div className="panel w-full lg:w-[280px] flex-shrink-0">
          <div className="lbl">Total on-ramped</div>
          <div className="font-serif text-[30px] leading-none mt-[7px]">{formatUsd(totalOnRamped)}</div>
          <div className="border-t border-sillage-line mt-[18px]">
            {[
              ['Deposits', String(depositCount)],
              ['Avg deposit', formatUsdPrecise(avgDeposit)],
              ['Net multiple', netMultiple > 0 ? `${netMultiple.toFixed(2)}×` : '—'],
              [
                'First deposit',
                firstDeposit ? format(new Date(firstDeposit.depositedAt), 'MMM yyyy') : '—',
              ],
            ].map(([label, val], idx, arr) => (
              <div
                key={label}
                className={`flex justify-between py-2.5 ${idx < arr.length - 1 ? 'border-b border-sillage-line' : ''}`}
              >
                <span className="lbl">{label}</span>
                <span
                  className={`font-mono tabular-nums text-xs ${label === 'Net multiple' && netMultiple > 1 ? 'text-sillage-green' : ''}`}
                >
                  {val}
                </span>
              </div>
            ))}
          </div>
          <div className="cap mt-4 leading-relaxed">
            Cost basis of the whole book. Every fiat entry is logged locally — nothing is inferred from an
            exchange.
          </div>
        </div>
      </div>

      <div className="panel mt-5">
        <div className="lbl mb-1">Table 3 · Deposit ledger</div>
        <div className="trow text-sillage-soft border-t-0">
          <div className="w-[104px] lbl text-[9px]">Date</div>
          <div className="flex-1 lbl text-[9px]">Method · venue</div>
          <div className="w-[110px] text-right lbl text-[9px]">Amount</div>
          <div className="w-[120px] text-right lbl text-[9px]">Cumulative</div>
        </div>
        {ledger.length === 0 ? (
          <div className="text-center py-8 text-sillage-soft text-sm">No fiat deposit rows stored.</div>
        ) : (
          ledger.map((r) => (
            <div key={r.id} className="trow">
              <div className="w-[104px] font-mono text-[11px] text-sillage-soft">{r.label}</div>
              <div className="flex-1 text-[13px]">{r.methodLabel}</div>
              <div className="w-[110px] text-right font-mono tabular-nums text-xs">
                {r.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{' '}
                {r.currency}
              </div>
              <div className="w-[120px] text-right font-mono tabular-nums text-xs text-sillage-soft">
                {r.cumulative.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
