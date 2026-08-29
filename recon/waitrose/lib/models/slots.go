package models

import "time"

type SlotDaysInput struct {
	BranchID        string   `json:"branchId,omitempty"`
	SlotType        string   `json:"slotType"`
	CustomerOrderID string   `json:"customerOrderId"`
	Postcode        string   `json:"postcode,omitempty"`
	AddressID       string   `json:"addressId,omitempty"`
	FromDate        string   `json:"fromDate"`
	Size            *int     `json:"size,omitempty"`
	SlotGridType    []string `json:"slotGridType,omitempty"`
}

type SlotDatesInput struct {
	BranchID        string `json:"branchId,omitempty"`
	SlotType        string `json:"slotType"`
	CustomerOrderID string `json:"customerOrderId"`
	FromDate        string `json:"fromDate,omitempty"`
	Size            *int   `json:"size,omitempty"`
	AddressID       string `json:"addressId,omitempty"`
}

type CurrentSlotInput struct {
	CustomerOrderID string `json:"customerOrderId"`
	CustomerID      string `json:"customerId,omitempty"`
}

type BookSlotInput struct {
	BranchID           string      `json:"branchId,omitempty"`
	SlotType           string      `json:"slotType"`
	SlotGridType       string      `json:"slotGridType,omitempty"`
	CustomerOrderID    string      `json:"customerOrderId"`
	Postcode           string      `json:"postcode,omitempty"`
	AddressID          string      `json:"addressId,omitempty"`
	StartDateTime      string      `json:"startDateTime"`
	EndDateTime        string      `json:"endDateTime"`
	ExpectedSlotCharge *PriceInput `json:"expectedSlotCharge,omitempty"`
	GreenSlot          *bool       `json:"greenSlot,omitempty"`
}

type PriceInput struct {
	Amount       float64 `json:"amount"`
	CurrencyCode string  `json:"currencyCode,omitempty"`
}

type SlotDaySlot struct {
	ID               string    `json:"id"`
	StartDateTime    time.Time `json:"startDateTime"`
	EndDateTime      time.Time `json:"endDateTime"`
	ShopByDateTime   time.Time `json:"shopByDateTime"`
	Status           string    `json:"status,omitempty"`
	SlotGridType     string    `json:"slotGridType,omitempty"`
	Charge           *Price    `json:"charge,omitempty"`
	GreenSlot        *bool     `json:"greenSlot,omitempty"`
	DeliveryPassSlot *bool     `json:"deliveryPassSlot,omitempty"`
}

type SlotDayContent struct {
	ID       string        `json:"id"`
	BranchID string        `json:"branchId,omitempty"`
	SlotType string        `json:"slotType,omitempty"`
	Date     string        `json:"date,omitempty"`
	Slots    []SlotDaySlot `json:"slots,omitempty"`
}

type SlotDayFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type SlotDays struct {
	Content  []SlotDayContent `json:"content,omitempty"`
	Failures []SlotDayFailure `json:"failures,omitempty"`
	Variant  string           `json:"variant,omitempty"`
}

type SlotDateContent struct {
	ID        string `json:"id,omitempty"`
	DayOfWeek string `json:"dayOfWeek,omitempty"`
}

type SlotDatesFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type SlotDates struct {
	Content  []SlotDateContent  `json:"content,omitempty"`
	Failures []SlotDatesFailure `json:"failures,omitempty"`
}

type SlotDaysData struct {
	SlotDays *SlotDays `json:"slotDays"`
}

type SlotDaysResponse struct {
	Data   *SlotDaysData  `json:"data,omitempty"`
	Errors []GraphQLError `json:"errors,omitempty"`
}

type SlotDatesData struct {
	SlotDates *SlotDates `json:"slotDates"`
}

type SlotDatesResponse struct {
	Data   *SlotDatesData `json:"data,omitempty"`
	Errors []GraphQLError `json:"errors,omitempty"`
}

type CurrentSlot struct {
	SlotType                 string    `json:"slotType,omitempty"`
	BranchID                 string    `json:"branchId,omitempty"`
	AddressID                string    `json:"addressId,omitempty"`
	Postcode                 string    `json:"postcode,omitempty"`
	StartDateTime            time.Time `json:"startDateTime"`
	EndDateTime              time.Time `json:"endDateTime"`
	ExpiryDateTime           time.Time `json:"expiryDateTime"`
	OrderCutoffDateTime      time.Time `json:"orderCutoffDateTime"`
	AmendOrderCutoffDateTime time.Time `json:"amendOrderCutoffDateTime"`
	ShopByDateTime           time.Time `json:"shopByDateTime"`
	SlotReservationID        string    `json:"slotReservationId,omitempty"`
	DeliveryCharge           *Price    `json:"deliveryCharge,omitempty"`
	SlotGridType             string    `json:"slotGridType,omitempty"`
	GreenSlot                *bool     `json:"greenSlot,omitempty"`
}

type CurrentSlotData struct {
	CurrentSlot *CurrentSlot `json:"currentSlot"`
}

type CurrentSlotResponse struct {
	Data   *CurrentSlotData `json:"data,omitempty"`
	Errors []GraphQLError   `json:"errors,omitempty"`
}

type BookSlotFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type BookSlotResult struct {
	SlotExpiryDateTime       time.Time         `json:"slotExpiryDateTime,omitempty"`
	OrderCutoffDateTime      time.Time         `json:"orderCutoffDateTime,omitempty"`
	AmendOrderCutoffDateTime time.Time         `json:"amendOrderCutoffDateTime,omitempty"`
	ShopByDateTime           time.Time         `json:"shopByDateTime,omitempty"`
	Failures                 []BookSlotFailure `json:"failures,omitempty"`
	Variant                  string            `json:"variant,omitempty"`
}

type BookSlotData struct {
	BookSlot *BookSlotResult `json:"bookSlot"`
}

type BookSlotResponse struct {
	Data   *BookSlotData  `json:"data,omitempty"`
	Errors []GraphQLError `json:"errors,omitempty"`
}
