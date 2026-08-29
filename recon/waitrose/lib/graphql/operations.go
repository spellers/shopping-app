package graphql

const NewSessionMutation = `mutation NewSession($input: SessionInput) {
  generateSession(session: $input) {
    __typename
    accessToken
    refreshToken
    customerId
    customerOrderId
    customerOrderState
    defaultBranchId
    expiresIn
    failures {
      type
      message
    }
  }
}`

const RefreshSessionMutation = `mutation RefreshSession($input: SessionInput) {
  generateSession(session: $input) {
    __typename
    accessToken
    refreshToken
    customerId
    customerOrderId
    customerOrderState
    defaultBranchId
    expiresIn
    failures {
      type
      message
    }
  }
}`

const DeleteSessionMutation = `mutation DeleteSession {
  deleteSession
}`

const GetTrolleyQuery = `query GetTrolley($orderId: ID!) {
  getTrolley(orderId: $orderId) {
    products {
      id
      lineNumber
      name
      displayPrice
    }
    trolley {
      orderId
      trolleyItems {
        lineNumber
        quantity {
          amount
          uom
        }
        totalPrice {
          amount
          currencyCode
        }
      }
      trolleyTotals {
        totalEstimatedCost {
          amount
          currencyCode
        }
      }
    }
    failures {
      type
      message
    }
  }
}`

const UpdateTrolleyItemsMutation = `mutation UpdateTrolleyItems($trolleyItemsInput: [TrolleyItemInput!], $orderId: ID!) {
  updateTrolleyItems(trolleyItems: $trolleyItemsInput, orderId: $orderId) {
    products {
      id
      lineNumber
      name
      displayPrice
    }
    trolley {
      orderId
      trolleyItems {
        lineNumber
        quantity {
          amount
          uom
        }
        totalPrice {
          amount
          currencyCode
        }
      }
      trolleyTotals {
        totalEstimatedCost {
          amount
          currencyCode
        }
      }
    }
    failures {
      type
      message
    }
  }
}`

const EmptyTrolleyMutation = `mutation EmptyTrolley {
  emptyTrolley {
    success
    failures {
      type
      message
    }
  }
}`

const SlotDaysQuery = `query SlotDays($slotDaysInput: SlotDaysInput) {
  slotDays(slotDaysInput: $slotDaysInput) {
    content {
      id
      branchId
      slotType
      date
      slots {
        id
        startDateTime
        endDateTime
        shopByDateTime
        status
        slotGridType
        charge {
          currencyCode
          amount
        }
        greenSlot
        deliveryPassSlot
      }
    }
    failures {
      message
      type
    }
    variant
  }
}`

const SlotDatesQuery = `query SlotDates($slotDatesInput: SlotDatesInput) {
  slotDates(slotDatesInput: $slotDatesInput) {
    content {
      id
      dayOfWeek
    }
    failures {
      message
      type
    }
  }
}`

const CurrentSlotQuery = `query CurrentSlot($input: CurrentSlotInput) {
  currentSlot(currentSlotInput: $input) {
    slotType
    branchId
    addressId
    postcode
    startDateTime
    endDateTime
    expiryDateTime
    orderCutoffDateTime
    amendOrderCutoffDateTime
    shopByDateTime
    slotReservationId
    deliveryCharge {
      amount
      currencyCode
    }
    slotGridType
    greenSlot
  }
}`

const BookSlotMutation = `mutation BookSlot($input: BookSlotInput) {
  bookSlot(bookSlotInput: $input) {
    slotExpiryDateTime
    orderCutoffDateTime
    amendOrderCutoffDateTime
    shopByDateTime
    failures {
      type
      message
    }
    variant
  }
}`

const GetOrdersQuery = `query GetOrders($getOrdersInput: GetOrdersInput) {
  getOrders(getOrdersInput: $getOrdersInput) {
    content {
      customerOrderId
      status
      created
      totals {
        estimated {
          totalPrice {
            amount
            currencyCode
          }
        }
      }
      slots {
        startDateTime
        endDateTime
        status
      }
    }
  }
}`

const GetOrderQuery = `query GetOrder($customerOrderId: String) {
  getOrder(customerOrderId: $customerOrderId) {
    customerOrderId
    status
    created
    lastUpdated
    containsEntertainingLines
    substitutionsAllowed
    bagless
    paperStatement
    orderLines {
      lineNumber
      orderLineStatus
      estimatedQuantity {
        amount
        uom
      }
      quantity {
        amount
        uom
      }
      estimatedUnitPrice {
        amount
        currencyCode
      }
      estimatedTotalPrice {
        amount
        currencyCode
      }
      price {
        amount
        currencyCode
      }
      totalPrice {
        amount
        currencyCode
      }
      substitutionAllowed
      noteToShopper
    }
    slots {
      branchId
      branchName
      type
      startDateTime
      endDateTime
      amendOrderCutoffDateTime
      status
      deliveryAddress {
        id
        line1
        line2
        line3
        postalCode
        town
        region
        country
      }
    }
    totals {
      actual {
        paid {
          amount
          currencyCode
        }
        savings {
          amount
          currencyCode
        }
        deliveryCharge {
          amount
          currencyCode
        }
      }
      estimated {
        totalPrice {
          amount
          currencyCode
        }
        toPay {
          amount
          currencyCode
        }
        deliveryCharge {
          amount
          currencyCode
        }
      }
    }
  }
}`

const GetProductsQuery = `query GetProducts($lineNumbers: [String!]!) {
  getProducts(lineNumbers: $lineNumbers) {
    lineNumber
    name
  }
}`

const CancelOrderMutation = `mutation CancelOrder($input: ID!) {
  cancelOrder(customerOrderId: $input) {
    failures {
      type
      message
    }
  }
}`
