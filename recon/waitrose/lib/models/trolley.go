package models

type QuantityInput struct {
	Amount float64 `json:"amount"`
	UOM    string  `json:"uom"`
}

type TrolleyItemInput struct {
	LineNumber          string         `json:"lineNumber,omitempty"`
	ProductID           string         `json:"productId,omitempty"`
	Quantity            *QuantityInput `json:"quantity,omitempty"`
	CanSubstitute       *bool          `json:"canSubstitute,omitempty"`
	NoteToShopper       string         `json:"noteToShopper,omitempty"`
	PersonalisedMessage string         `json:"personalisedMessage,omitempty"`
	RecipeID            string         `json:"recipeId,omitempty"`
	ReservedQuantity    *float64       `json:"reservedQuantity,omitempty"`
	TrolleyItemID       *int           `json:"trolleyItemId,omitempty"`
}

type TrolleyProduct struct {
	ID           string `json:"id"`
	LineNumber   string `json:"lineNumber,omitempty"`
	Name         string `json:"name"`
	DisplayPrice string `json:"displayPrice,omitempty"`
}

type Price struct {
	Amount       float64 `json:"amount"`
	CurrencyCode string  `json:"currencyCode,omitempty"`
}

type Quantity struct {
	Amount float64 `json:"amount"`
	UOM    string  `json:"uom"`
}

type TrolleyTotals struct {
	SubTotal           *Price `json:"subTotal,omitempty"`
	DeliveryCharge     *Price `json:"deliveryCharge,omitempty"`
	Total              *Price `json:"total,omitempty"`
	Savings            *Price `json:"savings,omitempty"`
	TotalEstimatedCost *Price `json:"totalEstimatedCost,omitempty"`
}

type TrolleyItem struct {
	LineNumber string    `json:"lineNumber"`
	Quantity   *Quantity `json:"quantity,omitempty"`
	TotalPrice *Price    `json:"totalPrice,omitempty"`
}

type Trolley struct {
	OrderID       string         `json:"orderId,omitempty"`
	TrolleyItems  []TrolleyItem  `json:"trolleyItems,omitempty"`
	TrolleyTotals *TrolleyTotals `json:"trolleyTotals,omitempty"`
}

type TrolleyFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type TrolleyResponse struct {
	Products []TrolleyProduct `json:"products,omitempty"`
	Trolley  *Trolley         `json:"trolley,omitempty"`
	Failures []TrolleyFailure `json:"failures,omitempty"`
}

type GetTrolleyData struct {
	GetTrolley *TrolleyResponse `json:"getTrolley"`
}

type GetTrolleyResponse struct {
	Data   *GetTrolleyData `json:"data,omitempty"`
	Errors []GraphQLError  `json:"errors,omitempty"`
}

type UpdateTrolleyItemsData struct {
	UpdateTrolleyItems *TrolleyResponse `json:"updateTrolleyItems"`
}

type UpdateTrolleyItemsResponse struct {
	Data   *UpdateTrolleyItemsData `json:"data,omitempty"`
	Errors []GraphQLError          `json:"errors,omitempty"`
}
