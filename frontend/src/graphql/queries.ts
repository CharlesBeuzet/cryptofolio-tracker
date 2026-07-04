import { gql } from '@apollo/client'

export const GET_PORTFOLIO = gql`
  query GetPortfolio {
    portfolio {
      totalValue
      todaysPnl
      todaysPnlPercent
      positions {
        id
        symbol
        quantity
        avgEntryPrice
        currentPrice
        pnl
        pnlPercent
        value
        firstBoughtAt
        exchange
        durationDays
      }
    }
  }
`

export const GET_POSITIONS = gql`
  query GetPositions {
    positions {
      id
      symbol
      quantity
      avgEntryPrice
      currentPrice
      pnl
      pnlPercent
      value
      firstBoughtAt
      exchange
      durationDays
      orders {
        id
        symbol
        type
        quantity
        price
        executedAt
        exchange
      }
    }
  }
`

export const GET_POSITION = gql`
  query GetPosition($id: Int!) {
    position(id: $id) {
      id
      symbol
      quantity
      avgEntryPrice
      currentPrice
      pnl
      pnlPercent
      value
      firstBoughtAt
      exchange
      durationDays
      metrics {
        avgExitPrice
      }
      orders {
        id
        symbol
        type
        quantity
        price
        executedAt
        exchange
      }
    }
  }
`

export const GET_PERFORMANCE = gql`
  query GetPerformance {
    performance {
      totalValue
      todaysPnl
      todaysPnlPercent
    }
  }
`

export const GET_PORTFOLIO_HISTORY = gql`
  query GetPortfolioHistory($days: Int!) {
    portfolioHistory(days: $days) {
      timestamp
      totalValue
    }
  }
`

export const GET_DAILY_PNL_HISTORY = gql`
  query GetDailyPnlHistory($days: Int!) {
    dailyPnlHistory(days: $days) {
      date
      pnl
      pnlPercent
    }
  }
`

export const GET_ASSET_PRICE_HISTORY = gql`
  query GetAssetPriceHistory($symbol: String!, $days: Int!) {
    assetPriceHistory(symbol: $symbol, days: $days) {
      symbol
      days
      isMock
      resolutionStatus
      ambiguityMessage
      candidates {
        id
        name
        symbol
      }
      points {
        timestamp
        price
      }
    }
  }
`

export const GET_FIAT_DEPOSITS_SUMMARY = gql`
  query GetFiatDepositsSummary {
    fiatDepositsSummary {
      includedRecordCount
      totalsByCurrency {
        currency
        totalAmount
      }
    }
  }
`

export const GET_FIAT_DEPOSITS = gql`
  query GetFiatDeposits($limit: Int!) {
    fiatDeposits(limit: $limit) {
      id
      exchange
      externalOrderId
      currency
      amount
      fee
      status
      method
      source
      depositedAt
      createdAt
    }
  }
`

