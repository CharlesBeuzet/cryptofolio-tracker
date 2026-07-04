import { useMemo, useState } from 'react'
import AssetPriceChart from '../components/charts/AssetPriceChart'
import RechartsPriceChart from '../components/charts/RechartsPriceChart'
import RangeSegment, { type RangeKey, rangeToDays } from '../components/common/RangeSegment'
import {
  MOCK_AVG_ENTRY,
  MOCK_SYMBOL,
  generateMockOrders,
  generateMockPriceHistory,
} from '../utils/mockChartData'

export default function ChartComparison() {
  const [range, setRange] = useState<RangeKey>('90d')
  const days = rangeToDays(range)

  const priceHistory = useMemo(() => generateMockPriceHistory(days), [days])
  const orders = useMemo(() => generateMockOrders(priceHistory), [priceHistory])

  return (
    <div>
      <div className="flex justify-between items-end mb-5">
        <div>
          <div className="lbl">Chart library comparison</div>
          <div className="font-serif text-[26px] leading-none mt-2">{MOCK_SYMBOL} · mocked price data</div>
          <p className="cap mt-2 max-w-xl">
            Same synthetic price curve and order markers rendered with Recharts (left) and Chart.js (right).
          </p>
        </div>
        <RangeSegment value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="panel">
          <div className="flex justify-between items-center mb-3.5">
            <div className="lbl">Recharts · ComposedChart</div>
            <div className="font-mono text-[11px] flex gap-4">
              <span><span className="text-sillage-green">●</span> buy</span>
              <span><span className="text-sillage-accent">●</span> sell</span>
            </div>
          </div>
          <RechartsPriceChart
            symbol={MOCK_SYMBOL}
            priceHistory={priceHistory}
            orders={orders}
            avgEntryPrice={MOCK_AVG_ENTRY}
          />
        </div>

        <div className="panel">
          <div className="flex justify-between items-center mb-3.5">
            <div className="lbl">Chart.js · line + scatter</div>
            <div className="font-mono text-[11px] flex gap-4">
              <span><span className="text-sillage-green">●</span> buy</span>
              <span><span className="text-sillage-accent">●</span> sell</span>
            </div>
          </div>
          <AssetPriceChart
            symbol={MOCK_SYMBOL}
            priceHistory={priceHistory}
            orders={orders}
            avgEntryPrice={MOCK_AVG_ENTRY}
            isMock
          />
        </div>
      </div>

      <div className="panel mt-5">
        <div className="lbl mb-3">Shared dataset</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
          <div>
            <div className="text-sillage-soft">Points</div>
            <div>{priceHistory.length}</div>
          </div>
          <div>
            <div className="text-sillage-soft">Orders</div>
            <div>{orders.length}</div>
          </div>
          <div>
            <div className="text-sillage-soft">Range low</div>
            <div>${Math.min(...priceHistory.map((p) => p.price)).toLocaleString()}</div>
          </div>
          <div>
            <div className="text-sillage-soft">Range high</div>
            <div>${Math.max(...priceHistory.map((p) => p.price)).toLocaleString()}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
