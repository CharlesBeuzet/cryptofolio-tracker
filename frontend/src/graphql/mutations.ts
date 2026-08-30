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
