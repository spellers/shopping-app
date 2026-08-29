package waitrose

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jingkaihe/waitrose/auth"
	"github.com/jingkaihe/waitrose/graphql"
	"github.com/jingkaihe/waitrose/models"
)

const (
	DefaultBaseURL                     = "https://www.waitrose.com/api/graphql-prod/graph/live"
	DefaultContentBaseURL              = "https://www.waitrose.com/api/content-prod/v2/cms/publish/productcontent/search"
	DefaultProductsBaseURL             = "https://www.waitrose.com/api/products-prod/v1/products"
	DefaultAddressesBaseURL            = "https://www.waitrose.com/api"
	DefaultAddressesEnv                = "prod"
	DefaultSlotOrchestrationBaseURL    = "https://www.waitrose.com/api/slot-orchestration-prod/v1"
	DefaultSlotOrchestrationBreadcrumb = "delivery-fe"
	DefaultAPIKey                      = "EbUnxV2CRy3jZk1kgfwaY5K1zTSlnnpx9uHS8Oth"
	DefaultUserAgent                   = "Waitrose/3.9.1.14114 Android"
	DefaultBreadcrumb                  = "android-grocery-app"
)

type Config struct {
	BaseURL                     string
	ContentBaseURL              string
	ProductsBaseURL             string
	AddressesBaseURL            string
	AddressesEnv                string
	SlotOrchestrationBaseURL    string
	SlotOrchestrationBreadcrumb string
	APIKey                      string
	UserAgent                   string
	HTTPClient                  *http.Client
}

type Client struct {
	baseURL                     string
	contentBaseURL              string
	productsBaseURL             string
	addressesBaseURL            string
	addressesEnv                string
	slotOrchestrationBaseURL    string
	slotOrchestrationBreadcrumb string
	apiKey                      string
	userAgent                   string
	httpClient                  *http.Client
	session                     *auth.Session
}

func NewClient(cfg Config) *Client {
	if cfg.BaseURL == "" {
		cfg.BaseURL = DefaultBaseURL
	}
	if cfg.ContentBaseURL == "" {
		cfg.ContentBaseURL = DefaultContentBaseURL
	}
	if cfg.ProductsBaseURL == "" {
		cfg.ProductsBaseURL = DefaultProductsBaseURL
	}
	if cfg.AddressesBaseURL == "" {
		cfg.AddressesBaseURL = DefaultAddressesBaseURL
	}
	if cfg.AddressesEnv == "" {
		cfg.AddressesEnv = DefaultAddressesEnv
	}
	if cfg.SlotOrchestrationBaseURL == "" {
		cfg.SlotOrchestrationBaseURL = DefaultSlotOrchestrationBaseURL
	}
	if cfg.SlotOrchestrationBreadcrumb == "" {
		cfg.SlotOrchestrationBreadcrumb = DefaultSlotOrchestrationBreadcrumb
	}
	if cfg.APIKey == "" {
		cfg.APIKey = DefaultAPIKey
	}
	if cfg.UserAgent == "" {
		cfg.UserAgent = DefaultUserAgent
	}
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 30 * time.Second}
	}
	return &Client{
		baseURL:                     cfg.BaseURL,
		contentBaseURL:              cfg.ContentBaseURL,
		productsBaseURL:             cfg.ProductsBaseURL,
		addressesBaseURL:            cfg.AddressesBaseURL,
		addressesEnv:                cfg.AddressesEnv,
		slotOrchestrationBaseURL:    cfg.SlotOrchestrationBaseURL,
		slotOrchestrationBreadcrumb: cfg.SlotOrchestrationBreadcrumb,
		apiKey:                      cfg.APIKey,
		userAgent:                   cfg.UserAgent,
		httpClient:                  cfg.HTTPClient,
		session:                     auth.NewSession(),
	}
}

func (c *Client) Session() *auth.Session {
	return c.session
}

type graphQLRequest struct {
	Query         string                 `json:"query"`
	OperationName string                 `json:"operationName,omitempty"`
	Variables     map[string]interface{} `json:"variables,omitempty"`
}

func (c *Client) doRequest(ctx context.Context, query string, variables map[string]interface{}, result interface{}) error {
	return c.doRequestWithToken(ctx, query, variables, result, "")
}

func (c *Client) doRequestWithToken(ctx context.Context, query string, variables map[string]interface{}, result interface{}, token string) error {
	reqBody := graphQLRequest{
		Query:     query,
		Variables: variables,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", DefaultBreadcrumb)

	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	} else if c.session.IsAuthenticated() {
		req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())
	} else {
		req.Header.Set("Authorization", "Bearer unauthenticated")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(respBody))
	}

	if err := json.Unmarshal(respBody, result); err != nil {
		return fmt.Errorf("unmarshal response: %w", err)
	}
	return nil
}

func (c *Client) Login(ctx context.Context, username, password string) (*models.SessionPayload, error) {
	clientID := "ANDROID_APP"
	variables := map[string]interface{}{
		"input": models.SessionInput{
			Username: &username,
			Password: &password,
			ClientID: &clientID,
		},
	}

	var resp models.NewSessionResponse
	if err := c.doRequest(ctx, graphql.NewSessionMutation, variables, &resp); err != nil {
		return nil, err
	}

	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}

	if resp.Data == nil || resp.Data.GenerateSession == nil {
		return nil, fmt.Errorf("no session data in response")
	}

	gs := resp.Data.GenerateSession
	if len(gs.Failures) > 0 {
		return nil, fmt.Errorf("session failure: %s - %s", gs.Failures[0].Type, gs.Failures[0].Message)
	}

	payload := &models.SessionPayload{
		AccessToken:        deref(gs.AccessToken),
		RefreshToken:       deref(gs.RefreshToken),
		CustomerID:         deref(gs.CustomerID),
		CustomerOrderID:    deref(gs.CustomerOrderID),
		CustomerOrderState: deref(gs.CustomerOrderState),
		DefaultBranchID:    deref(gs.DefaultBranchID),
		ExpiresIn:          derefInt(gs.ExpiresIn),
	}
	c.session.Update(payload)
	return payload, nil
}

func (c *Client) RefreshSession(ctx context.Context) (*models.SessionPayload, error) {
	clientID := "ANDROID_APP"
	customerID := c.session.CustomerID()
	refreshToken := c.session.RefreshToken()
	variables := map[string]interface{}{
		"input": models.SessionInput{
			ClientID:   &clientID,
			CustomerID: &customerID,
		},
	}

	var resp models.NewSessionResponse
	if err := c.doRequestWithToken(ctx, graphql.RefreshSessionMutation, variables, &resp, refreshToken); err != nil {
		return nil, err
	}

	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}

	if resp.Data == nil || resp.Data.GenerateSession == nil {
		return nil, fmt.Errorf("no session data in response")
	}

	gs := resp.Data.GenerateSession
	if len(gs.Failures) > 0 {
		return nil, fmt.Errorf("session failure: %s - %s", gs.Failures[0].Type, gs.Failures[0].Message)
	}

	payload := &models.SessionPayload{
		AccessToken:        deref(gs.AccessToken),
		RefreshToken:       deref(gs.RefreshToken),
		CustomerID:         deref(gs.CustomerID),
		CustomerOrderID:    deref(gs.CustomerOrderID),
		CustomerOrderState: deref(gs.CustomerOrderState),
		DefaultBranchID:    deref(gs.DefaultBranchID),
		ExpiresIn:          derefInt(gs.ExpiresIn),
	}
	c.session.Update(payload)
	return payload, nil
}

func (c *Client) Logout(ctx context.Context) error {
	if err := c.doRequest(ctx, graphql.DeleteSessionMutation, nil, &struct{}{}); err != nil {
		return err
	}
	c.session.Clear()
	return nil
}

func (c *Client) GetTrolley(ctx context.Context) (*models.TrolleyResponse, error) {
	orderId := c.session.CustomerOrderID()
	if orderId == "" {
		return nil, fmt.Errorf("no order ID in session, please login first")
	}
	variables := map[string]interface{}{
		"orderId": orderId,
	}
	var resp models.GetTrolleyResponse
	if err := c.doRequest(ctx, graphql.GetTrolleyQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.GetTrolley, nil
}

func (c *Client) UpdateTrolleyItems(ctx context.Context, items []models.TrolleyItemInput) (*models.TrolleyResponse, error) {
	orderID := c.session.CustomerOrderID()
	if orderID == "" {
		return nil, fmt.Errorf("no order ID in session, please login first")
	}
	variables := map[string]interface{}{
		"trolleyItemsInput": items,
		"orderId":           orderID,
	}
	var resp models.UpdateTrolleyItemsResponse
	if err := c.doRequest(ctx, graphql.UpdateTrolleyItemsMutation, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.UpdateTrolleyItems == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.UpdateTrolleyItems, nil
}

func (c *Client) SearchProducts(ctx context.Context, term string, start int, branchID string) (*models.SearchResults, error) {
	if term == "" {
		return nil, fmt.Errorf("search term is required")
	}
	customerID := c.session.CustomerID()
	if customerID == "" {
		return nil, fmt.Errorf("no customer ID in session, please login first")
	}
	if branchID == "" {
		branchID = c.session.DefaultBranchID()
	}

	if start < 0 {
		return nil, fmt.Errorf("start must be >= 0")
	}
	startPtr := &start

	var orderIDPtr *int
	if orderID := c.session.CustomerOrderID(); orderID != "" {
		if parsedOrderID, err := strconv.Atoi(orderID); err == nil {
			orderIDPtr = &parsedOrderID
		}
	}

	body := models.SearchRequestBody{
		CustomerSearchRequest: models.CustomerSearchRequest{
			QueryParams: models.QueryParams{
				SearchTerm: term,
				Start:      startPtr,
				BranchID:   branchID,
				OrderID:    orderIDPtr,
			},
		},
	}

	payload, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal search request: %w", err)
	}

	endpoint := strings.TrimRight(c.contentBaseURL, "/") + "/" + url.PathEscape(customerID) + "?clientType=WEB_APP"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("create search request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", DefaultBreadcrumb)
	if c.session.IsAuthenticated() {
		req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())
	} else {
		req.Header.Set("Authorization", "Bearer unauthenticated")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do search request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read search response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected search status %d: %s", resp.StatusCode, string(respBody))
	}

	var searchResp models.SearchResponse
	if err := json.Unmarshal(respBody, &searchResp); err != nil {
		return nil, fmt.Errorf("unmarshal search response: %w", err)
	}

	results := &models.SearchResults{
		TotalMatches: searchResp.TotalMatches,
	}
	for _, component := range searchResp.ComponentsAndProducts {
		if component.SearchProduct == nil {
			continue
		}
		results.Products = append(results.Products, *component.SearchProduct)
	}
	return results, nil
}

func (c *Client) GetSlotDays(ctx context.Context, input models.SlotDaysInput) (*models.SlotDays, error) {
	variables := map[string]interface{}{
		"slotDaysInput": input,
	}
	var resp models.SlotDaysResponse
	if err := c.doRequest(ctx, graphql.SlotDaysQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.SlotDays == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.SlotDays, nil
}

func (c *Client) GetSlotDates(ctx context.Context, input models.SlotDatesInput) (*models.SlotDates, error) {
	variables := map[string]interface{}{
		"slotDatesInput": input,
	}
	var resp models.SlotDatesResponse
	if err := c.doRequest(ctx, graphql.SlotDatesQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.SlotDates == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.SlotDates, nil
}

func (c *Client) GetCurrentSlot(ctx context.Context, input models.CurrentSlotInput) (*models.CurrentSlot, error) {
	variables := map[string]interface{}{
		"input": input,
	}
	var resp models.CurrentSlotResponse
	if err := c.doRequest(ctx, graphql.CurrentSlotQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.CurrentSlot == nil {
		return nil, nil
	}
	return resp.Data.CurrentSlot, nil
}

func (c *Client) BookSlot(ctx context.Context, input models.BookSlotInput) (*models.BookSlotResult, error) {
	variables := map[string]interface{}{
		"input": input,
	}
	var resp models.BookSlotResponse
	if err := c.doRequest(ctx, graphql.BookSlotMutation, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.BookSlot == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.BookSlot, nil
}

func (c *Client) CancelOrder(ctx context.Context, customerOrderID string) (*models.CancelOrderResult, error) {
	variables := map[string]interface{}{
		"input": customerOrderID,
	}
	var resp models.CancelOrderResponse
	if err := c.doRequest(ctx, graphql.CancelOrderMutation, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.CancelOrder == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.CancelOrder, nil
}

func (c *Client) CancelSlotReservation(ctx context.Context, reservationID string) error {
	if !c.session.IsAuthenticated() {
		return fmt.Errorf("not authenticated, please login first")
	}

	if reservationID == "" {
		return fmt.Errorf("reservation ID is required")
	}

	endpoint := strings.TrimRight(c.slotOrchestrationBaseURL, "/") + "/slot-reservations/" + reservationID
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, endpoint, nil)
	if err != nil {
		return fmt.Errorf("create slot cancellation request: %w", err)
	}

	req.Header.Set("Accept", "*/*")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", c.slotOrchestrationBreadcrumb)
	req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("do slot cancellation request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read slot cancellation response: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("unexpected slot cancellation status %d: %s", resp.StatusCode, string(respBody))
	}
	return nil
}

func (c *Client) GetOrders(ctx context.Context, input models.GetOrdersInput) (*models.OrdersPayload, error) {
	variables := map[string]interface{}{
		"getOrdersInput": input,
	}
	var resp models.GetOrdersResponse
	if err := c.doRequest(ctx, graphql.GetOrdersQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil {
		return nil, fmt.Errorf("no data in response")
	}
	return resp.Data.GetOrders, nil
}

func (c *Client) GetOrder(ctx context.Context, customerOrderID string) (*models.OrderDetail, error) {
	variables := map[string]interface{}{
		"customerOrderId": customerOrderID,
	}
	var resp models.GetOrderResponse
	if err := c.doRequest(ctx, graphql.GetOrderQuery, variables, &resp); err != nil {
		return nil, err
	}
	if len(resp.Errors) > 0 {
		return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
	}
	if resp.Data == nil || resp.Data.GetOrder == nil {
		return nil, fmt.Errorf("no order data in response")
	}
	return resp.Data.GetOrder, nil
}

func (c *Client) GetProducts(ctx context.Context, lineNumbers []string) (map[string]string, error) {
	if len(lineNumbers) == 0 {
		return make(map[string]string), nil
	}
	pathParts := make([]string, 0, len(lineNumbers))
	for _, lineNumber := range lineNumbers {
		if lineNumber == "" {
			continue
		}
		pathParts = append(pathParts, url.PathEscape(lineNumber))
	}
	if len(pathParts) == 0 {
		return make(map[string]string), nil
	}

	params := url.Values{}
	params.Set("view", "SUMMARY")
	params.Set("excludeLinesWithConflicts", "false")
	params.Set("filterByCustomerSlot", "true")

	endpoint := strings.TrimRight(c.productsBaseURL, "/") + "/" + strings.Join(pathParts, "+")
	if encoded := params.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("create product request: %w", err)
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", DefaultBreadcrumb)
	if c.session.IsAuthenticated() {
		req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())
	} else {
		req.Header.Set("Authorization", "Bearer unauthenticated")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do product request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read product response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected product status %d: %s", resp.StatusCode, string(respBody))
	}

	var productResp models.BatchProductDetailsResponse
	if err := json.Unmarshal(respBody, &productResp); err != nil {
		return nil, fmt.Errorf("unmarshal product response: %w", err)
	}

	result := make(map[string]string)
	for _, p := range productResp.Products {
		if p.LineNumber != "" && p.Name != "" {
			result[p.LineNumber] = p.Name
		}
	}
	return result, nil
}

func (c *Client) GetProductDetails(ctx context.Context, lineNumbers []string) ([]models.BatchProductDetail, error) {
	if len(lineNumbers) == 0 {
		return nil, nil
	}
	respBody, err := c.getProductDetailsResponse(ctx, lineNumbers)
	if err != nil {
		return nil, err
	}

	var productResp models.BatchProductDetailsResponse
	if err := json.Unmarshal(respBody, &productResp); err != nil {
		return nil, fmt.Errorf("unmarshal product details response: %w", err)
	}

	return productResp.Products, nil
}

func (c *Client) GetProductDetailsRaw(ctx context.Context, lineNumber string) (map[string]any, error) {
	if lineNumber == "" {
		return nil, fmt.Errorf("line number is required")
	}

	respBody, err := c.getProductDetailsResponse(ctx, []string{lineNumber})
	if err != nil {
		return nil, err
	}

	var envelope struct {
		Products []json.RawMessage `json:"products"`
	}
	if err := json.Unmarshal(respBody, &envelope); err != nil {
		return nil, fmt.Errorf("unmarshal product details response: %w", err)
	}
	if len(envelope.Products) == 0 {
		return nil, fmt.Errorf("product not found: %s", lineNumber)
	}

	var product map[string]any
	if err := json.Unmarshal(envelope.Products[0], &product); err != nil {
		return nil, fmt.Errorf("unmarshal product details payload: %w", err)
	}
	return product, nil
}

func (c *Client) getProductDetailsResponse(ctx context.Context, lineNumbers []string) ([]byte, error) {
	if len(lineNumbers) == 0 {
		return nil, nil
	}
	pathParts := make([]string, 0, len(lineNumbers))
	for _, lineNumber := range lineNumbers {
		if lineNumber == "" {
			continue
		}
		pathParts = append(pathParts, url.PathEscape(lineNumber))
	}
	if len(pathParts) == 0 {
		return nil, nil
	}

	params := url.Values{}
	params.Set("view", "EXTENDED")
	params.Set("filterByCustomerSlot", "true")
	if orderID := c.session.CustomerOrderID(); orderID != "" {
		params.Set("trolleyId", orderID)
	}

	endpoint := strings.TrimRight(c.productsBaseURL, "/") + "/" + strings.Join(pathParts, "+")
	if encoded := params.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("create product details request: %w", err)
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", DefaultBreadcrumb)
	if c.session.IsAuthenticated() {
		req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())
	} else {
		req.Header.Set("Authorization", "Bearer unauthenticated")
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do product details request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read product details response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected product details status %d: %s", resp.StatusCode, string(respBody))
	}

	return respBody, nil
}

func (c *Client) ListAddresses(ctx context.Context, sortBy string) ([]models.RemoteAddress, error) {
	if !c.session.IsAuthenticated() {
		return nil, fmt.Errorf("not authenticated, please login first")
	}

	endpoint := strings.TrimRight(c.addressesBaseURL, "/") + "/address-" + c.addressesEnv + "/v2/addresses"
	if sortBy != "" {
		params := url.Values{}
		params.Set("sortBy", sortBy)
		endpoint += "?" + params.Encode()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("create address request: %w", err)
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", c.userAgent)
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	req.Header.Set("client-correlation-id", uuid.New().String())
	req.Header.Set("breadcrumb", DefaultBreadcrumb)
	req.Header.Set("Authorization", "Bearer "+c.session.AccessToken())

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do address request: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read address response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected address status %d: %s", resp.StatusCode, string(respBody))
	}

	var addresses []models.RemoteAddress
	if err := json.Unmarshal(respBody, &addresses); err != nil {
		return nil, fmt.Errorf("unmarshal address response: %w", err)
	}
	return addresses, nil
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func derefInt(i *int) int {
	if i == nil {
		return 0
	}
	return *i
}
