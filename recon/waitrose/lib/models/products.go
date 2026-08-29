package models

type ProductPromotion struct {
	PromotionID          string `json:"promotionId,omitempty"`
	PromotionDescription string `json:"promotionDescription,omitempty"`
	PromotionExpiryDate  string `json:"promotionExpiryDate,omitempty"`
	PromotionType        string `json:"promotionType,omitempty"`
	PricePerUnit         string `json:"pricePerUnit,omitempty"`
	MyWaitrosePromotion  bool   `json:"myWaitrosePromotion,omitempty"`
	Price                *Price `json:"price,omitempty"`
}

type ProductNutrition struct {
	Per100gHeader    string `json:"per100gHeader,omitempty"`
	PerServingHeader string `json:"perServingHeader,omitempty"`
	NutrientsData    string `json:"nutrientsData,omitempty"`
}

type BatchProductDetail struct {
	LineNumber            string            `json:"lineNumber"`
	ID                    string            `json:"id,omitempty"`
	Name                  string            `json:"name"`
	Size                  string            `json:"size,omitempty"`
	Brand                 string            `json:"brand,omitempty"`
	Summary               string            `json:"summary,omitempty"`
	MarketingDescBop      string            `json:"marketingDescBop,omitempty"`
	Ingredients           string            `json:"ingredients,omitempty"`
	IngredientsNote       string            `json:"ingredientsNote,omitempty"`
	CookingInstructions   string            `json:"cookingInstructions,omitempty"`
	StorageInstruction    string            `json:"storageInstruction,omitempty"`
	Origins               string            `json:"origins,omitempty"`
	Statements            string            `json:"statements,omitempty"`
	DisplayPrice          string            `json:"displayPrice,omitempty"`
	DisplayPriceQualifier string            `json:"displayPriceQualifier,omitempty"`
	AverageRating         *float64          `json:"averageRating,omitempty"`
	ReviewCount           *int              `json:"reviewCount,omitempty"`
	ProductType           string            `json:"productType,omitempty"`
	Promotion             *ProductPromotion `json:"promotion,omitempty"`
	Nutrition             *ProductNutrition `json:"nutrition,omitempty"`
	ImageSmall            string            `json:"imageSmall,omitempty"`
	ImageMedium           string            `json:"imageMedium,omitempty"`
	ImageLarge            string            `json:"imageLarge,omitempty"`
}

type BatchProductDetailsResponse struct {
	Products []BatchProductDetail `json:"products"`
}
