import { gql } from '@apollo/client'

export const GET_SYNCED_VENUES = gql`
  query GetSyncedVenues {
    syncedVenues {
      key
      displayName
      kind
    }
  }
`

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
        source
        displayName
        externalUrl
        costBasis
        tag {
          id
          name
          description
        }
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
      source
      displayName
      externalUrl
      costBasis
      tag {
        id
        name
        description
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
      source
      displayName
      externalUrl
      costBasis
      tag {
        id
        name
        description
      }
      metrics {
        avgExitPrice
        cashInTrade
        realisedPnl
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
      valuations {
        id
        recordedAt
        valueAmount
        quantity
        createdAt
      }
    }
  }
`

export const GET_TAGS = gql`
  query GetTags {
    tags {
      id
      name
      description
    }
  }
`
export const GET_ASSET = gql`
  query GetAsset($symbol: String!) {
    asset(symbol: $symbol) {
      symbol
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
        source
        displayName
        externalUrl
        costBasis
        tag {
          id
          name
          description
        }
        valuations {
          id
          recordedAt
          valueAmount
          quantity
          createdAt
        metrics {
          cashInTrade
          realisedPnl
        }
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
  query GetAssetPriceHistory($symbol: String!, $days: Int!, $exchange: String) {
    assetPriceHistory(symbol: $symbol, days: $days, exchange: $exchange) {
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
        open
        high
        low
        close
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

export const GET_APP_CONFIG = gql`
  query GetAppConfig {
    appConfig {
      exists
      relativePath
      availableConnectors {
        name
        label
        supportsPassphrase
        supportsHostname
        supportsAddress
        requiredSecrets
      }
      exchanges {
        name
        label
        configured
        supportsPassphrase
        supportsHostname
        supportsAddress
        sandbox
        hostname
        address
        apiKey {
          isSet
          hint
        }
        apiSecret {
          isSet
          hint
        }
        passphrase {
          isSet
          hint
        }
      }
    }
  }
`

export const UPDATE_APP_CONFIG = gql`
  mutation UpdateAppConfig(
    $exchanges: [ExchangeConnectorInput!]
    $replaceExchanges: Boolean
  ) {
    updateAppConfig(
      exchanges: $exchanges
      replaceExchanges: $replaceExchanges
    ) {
      success
      message
      config {
        exists
        relativePath
        availableConnectors {
          name
          label
          supportsPassphrase
          supportsHostname
          supportsAddress
          requiredSecrets
        }
        exchanges {
          name
          label
          configured
          supportsPassphrase
          supportsHostname
          supportsAddress
          sandbox
          hostname
          address
          apiKey {
            isSet
            hint
          }
          apiSecret {
            isSet
            hint
          }
          passphrase {
            isSet
            hint
          }
        }
      }
    }
  }
`

