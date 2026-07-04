import { useEffect, useMemo, useRef } from 'react'
import {
  Chart as ChartJS,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import annotationPlugin from 'chartjs-plugin-annotation'
import { format } from 'date-fns'
import { formatUsdPrecise } from '../../utils/format'

ChartJS.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend,
  annotationPlugin,
)

interface PricePoint {
  timestamp: string
  price: number
}

interface Order {
  executedAt: string
  type: string
  price: number
  quantity: number
}

interface AssetPriceChartProps {
  symbol: string
  priceHistory: PricePoint[]
  orders: Order[]
  avgEntryPrice: number
  isMock?: boolean
  loading?: boolean
}

function cssVar(name: string): string {
  if (typeof document === 'undefined') return ''
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function buildDemoOrders(priceHistory: PricePoint[]): Order[] {
  if (priceHistory.length < 4) return []

  const picks = [
    Math.floor(priceHistory.length * 0.15),
    Math.floor(priceHistory.length * 0.4),
    Math.floor(priceHistory.length * 0.62),
    Math.floor(priceHistory.length * 0.85),
  ]

  return picks.map((index, i) => {
    const point = priceHistory[index]
    return {
      executedAt: point.timestamp,
      type: i % 3 === 2 ? 'sell' : 'buy',
      price: point.price,
      quantity: 0.5 + i * 0.25,
    }
  })
}

export default function AssetPriceChart({
  symbol,
  priceHistory,
  orders,
  avgEntryPrice,
  isMock = false,
  loading = false,
}: AssetPriceChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<ChartJS | null>(null)

  const displayOrders = useMemo(() => {
    if (orders.length > 0) return orders
    if (isMock) return buildDemoOrders(priceHistory)
    return []
  }, [orders, isMock, priceHistory])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || priceHistory.length === 0) return

    const green = cssVar('--green') || '#4fbe86'
    const accent = cssVar('--accent') || '#e0a35e'
    const soft = cssVar('--soft') || '#86988e'
    const line = cssVar('--line') || 'rgba(170, 200, 188, 0.14)'
    const card = cssVar('--card') || '#0f1f1d'
    const ink = cssVar('--ink') || '#e9e5d7'

    const buyOrders = displayOrders.filter((o) => o.type === 'buy')
    const sellOrders = displayOrders.filter((o) => o.type === 'sell')

    const data: ChartData<'line'> = {
      datasets: [
        {
          label: `${symbol} price`,
          data: priceHistory.map((p) => ({ x: new Date(p.timestamp).getTime(), y: p.price })),
          borderColor: green,
          backgroundColor: 'transparent',
          borderWidth: 1.8,
          pointRadius: 0,
          pointHoverRadius: 3,
          tension: 0.25,
          order: 2,
        },
        {
          label: 'Buy',
          data: buyOrders.map((o) => ({
            x: new Date(o.executedAt).getTime(),
            y: o.price,
          })),
          borderColor: green,
          backgroundColor: green,
          pointRadius: 6,
          pointHoverRadius: 7,
          showLine: false,
          order: 1,
        },
        {
          label: 'Sell',
          data: sellOrders.map((o) => ({
            x: new Date(o.executedAt).getTime(),
            y: o.price,
          })),
          borderColor: accent,
          backgroundColor: accent,
          pointRadius: 6,
          pointHoverRadius: 7,
          showLine: false,
          order: 1,
        },
      ],
    }

    const options: ChartOptions<'line'> = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: card,
          borderColor: line,
          borderWidth: 1,
          titleColor: ink,
          bodyColor: ink,
          titleFont: { family: 'IBM Plex Mono, monospace', size: 11 },
          bodyFont: { family: 'IBM Plex Mono, monospace', size: 11 },
          callbacks: {
            title: (items) => {
              const x = items[0]?.parsed.x
              if (x == null) return ''
              return format(new Date(x), 'MMM dd, yyyy HH:mm')
            },
            label: (ctx) => {
              const value = ctx.parsed.y
              if (value == null) return ''
              const label = ctx.dataset.label || 'Price'
              return `${label}: ${formatUsdPrecise(value)}`
            },
          },
        },
        annotation: {
          annotations: {
            avgEntry: {
              type: 'line',
              yMin: avgEntryPrice,
              yMax: avgEntryPrice,
              borderColor: accent,
              borderWidth: 1,
              borderDash: [4, 4],
              label: {
                display: true,
                content: 'Avg',
                position: 'end',
                color: soft,
                font: { size: 9, family: 'IBM Plex Mono, monospace' },
                backgroundColor: 'transparent',
              },
            },
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          grid: { color: line, drawTicks: false },
          border: { display: false },
          ticks: {
            color: soft,
            font: { size: 9, family: 'IBM Plex Mono, monospace' },
            maxTicksLimit: 6,
          },
        },
        y: {
          grid: { color: line, drawTicks: false },
          border: { display: false },
          ticks: {
            color: soft,
            font: { size: 9, family: 'IBM Plex Mono, monospace' },
            callback: (value) => `$${Number(value).toLocaleString()}`,
          },
        },
      },
    }

    chartRef.current?.destroy()
    chartRef.current = new ChartJS(canvas, { type: 'line', data, options })

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [symbol, priceHistory, displayOrders, avgEntryPrice])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm font-mono">
        Loading price history…
      </div>
    )
  }

  if (priceHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-sillage-soft text-sm">
        No price data available
      </div>
    )
  }

  return (
    <div className="relative h-[300px] w-full">
      {isMock && (
        <div className="absolute top-0 right-0 z-10 font-mono text-[9px] uppercase tracking-wider text-sillage-soft">
          demo data
        </div>
      )}
      <canvas ref={canvasRef} />
    </div>
  )
}
