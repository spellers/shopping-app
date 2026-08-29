package models

type SearchRequestBody struct {
	CustomerSearchRequest CustomerSearchRequest `json:"customerSearchRequest"`
}

type CustomerSearchRequest struct {
	QueryParams QueryParams `json:"queryParams"`
}

type QueryParams struct {
	SearchTerm string `json:"searchTerm,omitempty"`
	SortBy     string `json:"sortBy,omitempty"`
	Start      *int   `json:"start,omitempty"`
	BranchID   string `json:"branchId,omitempty"`
	OrderID    *int   `json:"orderId,omitempty"`
}

type SearchProduct struct {
	LineNumber   string `json:"lineNumber"`
	ProductID    string `json:"id,omitempty"`
	Name         string `json:"name"`
	DisplayPrice string `json:"displayPrice,omitempty"`
	Size         string `json:"size,omitempty"`
	Brand        string `json:"brand,omitempty"`
}

type SearchComponent struct {
	SearchProduct *SearchProduct `json:"searchProduct"`
}

type SearchResponse struct {
	ComponentsAndProducts []SearchComponent `json:"componentsAndProducts"`
	TotalMatches          int               `json:"totalMatches"`
}

type SearchResults struct {
	Products     []SearchProduct `json:"products"`
	TotalMatches int             `json:"totalMatches"`
}
