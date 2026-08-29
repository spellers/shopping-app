package models

type Addressee struct {
	ContactNumber string `json:"contactNumber,omitempty"`
	FirstName     string `json:"firstName,omitempty"`
	LastName      string `json:"lastName,omitempty"`
	Modified      string `json:"modified,omitempty"`
	Title         string `json:"title,omitempty"`
}

type RemoteAddress struct {
	AddressID string     `json:"id"`
	Line1     string     `json:"line1,omitempty"`
	Line2     string     `json:"line2,omitempty"`
	Line3     string     `json:"line3,omitempty"`
	Town      string     `json:"town,omitempty"`
	Region    string     `json:"region,omitempty"`
	Postcode  string     `json:"postalCode,omitempty"`
	Country   string     `json:"country,omitempty"`
	Addressee *Addressee `json:"addressee,omitempty"`
}
