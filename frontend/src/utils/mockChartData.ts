/** Synthetic price history and orders for chart library comparisons. */

export interface MockPricePoint {
  timestamp: string
  price: number
}

export interface MockOrder {
  executedAt: string
  type: 'buy' | 'sell'
  price: number
  quantity: number
}

const AVG_ENTRY = 72_400

export function generateMockPriceHistory(days = 90): MockPricePoint[] {
  const now = Date.now()
  const msPerDay = 86_400_000
  const points: MockPricePoint[] = []

  let price = 68_500
  for (let day = days; day >= 0; day -= 1) {
    const ts = new Date(now - day * msPerDay)
    const progress = (days - day) / days
    const trend = progress * 9_800
    const wave = Math.sin(day / 6) * 2_200 + Math.cos(day / 14) * 1_100
    const dip = day > 22 && day < 30 ? -4_500 : 0
    const spike = day > 55 && day < 58 ? 3_200 : 0
    price = 68_500 + trend + wave + dip + spike + ((day * 37) % 900) - 450
    points.push({ timestamp: ts.toISOString(), price: Math.round(price * 100) / 100 })
  }

  return points
}

export function generateMockOrders(priceHistory: MockPricePoint[]): MockOrder[] {
  const picks = [0.12, 0.28, 0.45, 0.61, 0.78, 0.9]
  return picks.map((ratio, index) => {
    const point = priceHistory[Math.floor(priceHistory.length * ratio)]
    return {
      executedAt: point.timestamp,
      type: index === 2 || index === 5 ? 'sell' : 'buy',
      price: point.price,
      quantity: 0.15 + index * 0.08,
    }
  })
}

export const MOCK_SYMBOL = 'BTC'
export const MOCK_AVG_ENTRY = AVG_ENTRY
