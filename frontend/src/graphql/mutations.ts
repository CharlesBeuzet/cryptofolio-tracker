import { gql } from '@apollo/client'

export const CREATE_TAG = gql`
  mutation CreateTag($name: String!, $description: String) {
    createTag(name: $name, description: $description) {
      id
      name
      description
    }
  }
`

export const UPDATE_TAG = gql`
  mutation UpdateTag($id: Int!, $name: String, $description: String) {
    updateTag(id: $id, name: $name, description: $description) {
      id
      name
      description
    }
  }
`

export const DELETE_TAG = gql`
  mutation DeleteTag($id: Int!) {
    deleteTag(id: $id)
  }
`

export const SET_POSITION_TAG = gql`
  mutation SetPositionTag($positionId: Int!, $tagId: Int) {
    setPositionTag(positionId: $positionId, tagId: $tagId) {
      id
      tag {
        id
        name
        description
      }
    }
  }
`

export const CREATE_MANUAL_POSITION = gql`
  mutation CreateManualPosition(
    $displayName: String!
    $symbol: String!
    $exchange: String!
    $externalUrl: String
    $initialValue: Float
    $initialQuantity: Float
    $recordedAt: DateTime
  ) {
    createManualPosition(
      displayName: $displayName
      symbol: $symbol
      exchange: $exchange
      externalUrl: $externalUrl
      initialValue: $initialValue
      initialQuantity: $initialQuantity
      recordedAt: $recordedAt
    ) {
      id
      symbol
      displayName
      exchange
      source
      value
      quantity
      costBasis
    }
  }
`

export const UPDATE_MANUAL_POSITION = gql`
  mutation UpdateManualPosition(
    $id: Int!
    $displayName: String
    $symbol: String
    $exchange: String
    $externalUrl: String
  ) {
    updateManualPosition(
      id: $id
      displayName: $displayName
      symbol: $symbol
      exchange: $exchange
      externalUrl: $externalUrl
    ) {
      id
      symbol
      displayName
      exchange
      source
      externalUrl
    }
  }
`

export const DELETE_MANUAL_POSITION = gql`
  mutation DeleteManualPosition($id: Int!) {
    deleteManualPosition(id: $id)
  }
`

export const ADD_POSITION_VALUATION = gql`
  mutation AddPositionValuation(
    $positionId: Int!
    $valueAmount: Float!
    $recordedAt: DateTime
    $quantity: Float
  ) {
    addPositionValuation(
      positionId: $positionId
      valueAmount: $valueAmount
      recordedAt: $recordedAt
      quantity: $quantity
    ) {
      id
      quantity
      value
      costBasis
      pnl
      pnlPercent
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

export const ADD_ONCHAIN_BUY_ORDER = gql`
  mutation AddOnchainBuyOrder(
    $positionId: Int!
    $quantity: Float!
    $price: Float!
    $executedAt: DateTime
  ) {
    addOnchainBuyOrder(
      positionId: $positionId
      quantity: $quantity
      price: $price
      executedAt: $executedAt
    ) {
      id
      quantity
      avgEntryPrice
      costBasis
      pnl
      pnlPercent
      unpricedQuantity
      orders {
        id
        symbol
        type
        quantity
        price
        executedAt
        exchange
        externalOrderId
      }
      metrics {
        avgExitPrice
        cashInTrade
        realisedPnl
        orderDerivedQty
      }
    }
  }
`

export const DELETE_ONCHAIN_MANUAL_ORDER = gql`
  mutation DeleteOnchainManualOrder($id: Int!) {
    deleteOnchainManualOrder(id: $id) {
      id
      quantity
      avgEntryPrice
      costBasis
      pnl
      pnlPercent
      unpricedQuantity
      orders {
        id
        symbol
        type
        quantity
        price
        executedAt
        exchange
        externalOrderId
      }
      metrics {
        avgExitPrice
        cashInTrade
        realisedPnl
        orderDerivedQty
      }
    }
  }
`

export const DELETE_POSITION_VALUATION = gql`
  mutation DeletePositionValuation($id: Int!) {
    deletePositionValuation(id: $id) {
      id
      quantity
      value
      costBasis
      pnl
      pnlPercent
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
