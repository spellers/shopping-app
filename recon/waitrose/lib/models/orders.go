package models

import "time"

type GetOrdersInput struct {
	Size     *int     `json:"size,omitempty"`
	SortBy   *string  `json:"sortBy,omitempty"`
	Start    *int     `json:"start,omitempty"`
	Statuses []string `json:"statuses,omitempty"`
}

type OrderPrice struct {
	Amount       float64 `json:"amount"`
	CurrencyCode string  `json:"currencyCode,omitempty"`
}

type OrderTotalsEstimated struct {
	TotalPrice *OrderPrice `json:"totalPrice,omitempty"`
	ToPay      *OrderPrice `json:"toPay,omitempty"`
}

type OrderTotals struct {
	Estimated *OrderTotalsEstimated `json:"estimated,omitempty"`
}

type OrderSlot struct {
	StartDateTime time.Time `json:"startDateTime"`
	EndDateTime   time.Time `json:"endDateTime"`
	Status        string    `json:"status,omitempty"`
}

type Order struct {
	CustomerOrderID string       `json:"customerOrderId"`
	Status          string       `json:"status"`
	Created         time.Time    `json:"created"`
	Totals          *OrderTotals `json:"totals,omitempty"`
	Slots           []OrderSlot  `json:"slots,omitempty"`
}

type OrdersPayload struct {
	Content []Order `json:"content,omitempty"`
}

type GetOrdersData struct {
	GetOrders *OrdersPayload `json:"getOrders"`
}

type GetOrdersResponse struct {
	Data   *GetOrdersData `json:"data,omitempty"`
	Errors []GraphQLError `json:"errors,omitempty"`
}

// OrderDetail types for GetOrder query
type OrderDetailQuantity struct {
	Amount float64 `json:"amount"`
	UOM    string  `json:"uom,omitempty"`
}

type OrderDetailPrice struct {
	Amount       float64 `json:"amount"`
	CurrencyCode string  `json:"currencyCode,omitempty"`
}

type OrderLine struct {
	LineNumber          string               `json:"lineNumber"`
	OrderLineStatus     string               `json:"orderLineStatus,omitempty"`
	EstimatedQuantity   *OrderDetailQuantity `json:"estimatedQuantity,omitempty"`
	Quantity            *OrderDetailQuantity `json:"quantity,omitempty"`
	EstimatedUnitPrice  *OrderDetailPrice    `json:"estimatedUnitPrice,omitempty"`
	EstimatedTotalPrice *OrderDetailPrice    `json:"estimatedTotalPrice,omitempty"`
	Price               *OrderDetailPrice    `json:"price,omitempty"`
	TotalPrice          *OrderDetailPrice    `json:"totalPrice,omitempty"`
	SubstitutionAllowed *bool                `json:"substitutionAllowed,omitempty"`
	NoteToShopper       string               `json:"noteToShopper,omitempty"`
}

type OrderAddress struct {
	ID         string `json:"id,omitempty"`
	Line1      string `json:"line1,omitempty"`
	Line2      string `json:"line2,omitempty"`
	Line3      string `json:"line3,omitempty"`
	PostalCode string `json:"postalCode,omitempty"`
	Town       string `json:"town,omitempty"`
	Region     string `json:"region,omitempty"`
	Country    string `json:"country,omitempty"`
}

type OrderDetailSlot struct {
	BranchID                 int           `json:"branchId,omitempty"`
	BranchName               string        `json:"branchName,omitempty"`
	Type                     string        `json:"type,omitempty"`
	StartDateTime            time.Time     `json:"startDateTime"`
	EndDateTime              time.Time     `json:"endDateTime"`
	AmendOrderCutoffDateTime *time.Time    `json:"amendOrderCutoffDateTime,omitempty"`
	Status                   string        `json:"status,omitempty"`
	DeliveryAddress          *OrderAddress `json:"deliveryAddress,omitempty"`
}

type OrderActualTotals struct {
	Paid           *OrderDetailPrice `json:"paid,omitempty"`
	Savings        *OrderDetailPrice `json:"savings,omitempty"`
	DeliveryCharge *OrderDetailPrice `json:"deliveryCharge,omitempty"`
}

type OrderEstimatedTotals struct {
	TotalPrice     *OrderDetailPrice `json:"totalPrice,omitempty"`
	ToPay          *OrderDetailPrice `json:"toPay,omitempty"`
	DeliveryCharge *OrderDetailPrice `json:"deliveryCharge,omitempty"`
}

type OrderDetailTotals struct {
	Actual    *OrderActualTotals    `json:"actual,omitempty"`
	Estimated *OrderEstimatedTotals `json:"estimated,omitempty"`
}

type OrderDetail struct {
	CustomerOrderID           string             `json:"customerOrderId"`
	Status                    string             `json:"status"`
	Created                   time.Time          `json:"created"`
	LastUpdated               time.Time          `json:"lastUpdated"`
	ContainsEntertainingLines *bool              `json:"containsEntertainingLines,omitempty"`
	SubstitutionsAllowed      bool               `json:"substitutionsAllowed"`
	Bagless                   bool               `json:"bagless"`
	PaperStatement            bool               `json:"paperStatement"`
	OrderLines                []OrderLine        `json:"orderLines,omitempty"`
	Slots                     []OrderDetailSlot  `json:"slots,omitempty"`
	Totals                    *OrderDetailTotals `json:"totals,omitempty"`
}

type GetOrderData struct {
	GetOrder *OrderDetail `json:"getOrder"`
}

type GetOrderResponse struct {
	Data   *GetOrderData  `json:"data,omitempty"`
	Errors []GraphQLError `json:"errors,omitempty"`
}

type ProductInfo struct {
	LineNumber string `json:"lineNumber"`
	Name       string `json:"name"`
}

type GetProductsData struct {
	GetProducts []ProductInfo `json:"getProducts"`
}

type GetProductsResponse struct {
	Data   *GetProductsData `json:"data,omitempty"`
	Errors []GraphQLError   `json:"errors,omitempty"`
}

type OrderFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type CancelOrderResult struct {
	Failures []OrderFailure `json:"failures,omitempty"`
}

type CancelOrderData struct {
	CancelOrder *CancelOrderResult `json:"cancelOrder"`
}

type CancelOrderResponse struct {
	Data   *CancelOrderData `json:"data,omitempty"`
	Errors []GraphQLError   `json:"errors,omitempty"`
}
