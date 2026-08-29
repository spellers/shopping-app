package models

type SessionInput struct {
	Username   *string `json:"username,omitempty"`
	Password   *string `json:"password,omitempty"`
	ClientID   *string `json:"clientId,omitempty"`
	CustomerID *string `json:"customerId,omitempty"`
}

type SessionPayload struct {
	AccessToken        string `json:"accessToken"`
	RefreshToken       string `json:"refreshToken"`
	CustomerID         string `json:"customerId"`
	CustomerOrderID    string `json:"customerOrderId"`
	CustomerOrderState string `json:"customerOrderState"`
	DefaultBranchID    string `json:"defaultBranchId"`
	ExpiresIn          int    `json:"expiresIn"`
}

type SessionFailure struct {
	Type    string `json:"type"`
	Message string `json:"message"`
}

type GenerateSessionResponse struct {
	Typename           string           `json:"__typename"`
	SessionPayload     *SessionPayload  `json:"sessionPayload,omitempty"`
	Failures           []SessionFailure `json:"failures,omitempty"`
	AccessToken        *string          `json:"accessToken,omitempty"`
	RefreshToken       *string          `json:"refreshToken,omitempty"`
	CustomerID         *string          `json:"customerId,omitempty"`
	CustomerOrderID    *string          `json:"customerOrderId,omitempty"`
	CustomerOrderState *string          `json:"customerOrderState,omitempty"`
	DefaultBranchID    *string          `json:"defaultBranchId,omitempty"`
	ExpiresIn          *int             `json:"expiresIn,omitempty"`
}

type NewSessionData struct {
	GenerateSession *GenerateSessionResponse `json:"generateSession"`
}

type NewSessionResponse struct {
	Data   *NewSessionData `json:"data,omitempty"`
	Errors []GraphQLError  `json:"errors,omitempty"`
}

type GraphQLError struct {
	Message    string                 `json:"message"`
	Path       []interface{}          `json:"path,omitempty"`
	Extensions map[string]interface{} `json:"extensions,omitempty"`
}
