import { gql } from '@apollo/client'

export const CREATE_TAG = gql`
  mutation CreateTag($name: String!, $description: String, $sortOrder: Int) {
    createTag(name: $name, description: $description, sortOrder: $sortOrder) {
      id
      name
      description
      sortOrder
    }
  }
`

export const UPDATE_TAG = gql`
  mutation UpdateTag(
    $id: Int!
    $name: String
    $description: String
    $sortOrder: Int
  ) {
    updateTag(id: $id, name: $name, description: $description, sortOrder: $sortOrder) {
      id
      name
      description
      sortOrder
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
        sortOrder
      }
    }
  }
`
