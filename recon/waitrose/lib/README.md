# Waitrose Go Client

A Go client library and CLI for the Waitrose & Partners grocery API, reverse-engineered from the official Android app.

## Installation

```bash
go install github.com/jingkaihe/waitrose/cmd/waitrose@latest
```

Or import the library:

```bash
go get github.com/jingkaihe/waitrose
```

## CLI Usage

### Commands

```bash
# Login to Waitrose
waitrose login -u email@example.com -p password

# Check session status
waitrose status

# Check version
waitrose version

# Search for products
waitrose search "organic eggs" --json

# Add items to trolley (use product-id from search results)
waitrose trolley add 468390-810671-810672
waitrose trolley add 468390-810671-810672 --qty 2

# Remove items from trolley
waitrose trolley remove 468390-810671-810672
waitrose trolley remove 468390-810671-810672 --qty 1

# Update item quantity in trolley
waitrose trolley update 468390-810671-810672 --qty 2

# View shopping trolley
waitrose trolley

# List saved addresses (get address-id for delivery slots)
waitrose address list

# View available delivery slots (--address required for delivery)
waitrose slot list --address <address-id>
waitrose slot list --address <address-id> --days 7 --from 2025-01-01

# Book a delivery slot
waitrose slot book <slot-id> --address <address-id>

# View the current booked slot
waitrose slot get

# Cancel a slot reservation
waitrose slot cancel
waitrose slot cancel <reservationId>

# View order history
waitrose order list -l 10

# View order details
waitrose order get 1032591263

# Logout
waitrose logout
```

### Global Flags

```bash
--api-key string   # Waitrose API key (or set WAITROSE_API_KEY env var)
-j, --json         # Output in JSON format
```

### Environment Variables

```bash
export WAITROSE_API_KEY="your-api-key"      # Optional API key (defaults to the app's prod key)
export WAITROSE_USERNAME="email"            # For login without -u flag
export WAITROSE_PASSWORD="password"         # For login without -p flag
export WAITROSE_JSON_OUTPUT="true"          # Output in JSON format by default
```

Session tokens are stored in `~/.waitrose/session.json` and automatically refreshed.

## Library Usage

```go
package main

import (
    "context"
    "fmt"
    "log"

    waitrose "github.com/jingkaihe/waitrose"
    "github.com/jingkaihe/waitrose/models"
)

func main() {
    client := waitrose.NewClient(waitrose.Config{
        APIKey: "your-api-key", // Optional
    })

    ctx := context.Background()

    // Login
    session, err := client.Login(ctx, "email@example.com", "password")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Logged in as: %s\n", session.CustomerID)

    // Get trolley (shopping cart)
    trolley, err := client.GetTrolley(ctx)
    if err != nil {
        log.Fatal(err)
    }
    fmt.Printf("Cart has %d items\n", trolley.Trolley.ItemCount)

    // Update trolley (product-id format: lineNumber-xxx-xxx)
    items := []models.TrolleyItemInput{
        {
            LineNumber: "468390",
            ProductID:  "468390-810671-810672",
            Quantity:   &models.QuantityInput{Amount: 2, UOM: "C62"}, // C62 = each
        },
    }
    _, err = client.UpdateTrolleyItems(ctx, items)
    if err != nil {
        log.Fatal(err)
    }

    // Get delivery slot days
    days := 7
    slotDays, err := client.GetSlotDays(ctx, models.SlotDaysInput{
        BranchID:        session.DefaultBranchID,
        SlotType:        "DELIVERY",
        CustomerOrderID: session.CustomerOrderID,
        FromDate:        time.Now().Format("2006-01-02"),
        Size:            &days,
    })
    if err != nil {
        log.Fatal(err)
    }
    for _, day := range slotDays.Content {
        fmt.Printf("%s: %d slots available\n", day.Date, len(day.Slots))
    }

    // Get orders
    orders, err := client.GetOrders(ctx, models.GetOrdersInput{
        CustomerID: session.CustomerID,
        Limit:      10,
    })
    if err != nil {
        log.Fatal(err)
    }
    for _, order := range orders.Orders {
        fmt.Printf("Order %s: %s\n", order.OrderNumber, order.Status)
    }

    // Logout
    if err := client.Logout(ctx); err != nil {
        log.Fatal(err)
    }
}
```

## API Reference

### Client Methods

| Method | Description |
|--------|-------------|
| `NewClient(cfg Config)` | Create a new client instance |
| `Login(ctx, username, password)` | Authenticate with email and password |
| `RefreshSession(ctx)` | Refresh the access token |
| `Logout(ctx)` | End the session |
| `GetTrolley(ctx)` | Get shopping cart contents |
| `UpdateTrolleyItems(ctx, items)` | Add/update cart items |
| `GetSlotDays(ctx, input)` | Get delivery slot days and slot details |
| `GetSlotDates(ctx, input)` | Get delivery slot dates |
| `BookSlot(ctx, input)` | Book a delivery slot |
| `GetOrders(ctx, input)` | Get order history |
| `GetOrder(ctx, orderID)` | Get order details |
| `CancelOrder(ctx, orderID)` | Cancel an order |

### Session Management

```go
client.Session().IsAuthenticated() // Check if logged in
client.Session().IsExpired()       // Check if token needs refresh
client.Session().CustomerID()      // Get customer ID
client.Session().DefaultBranchID() // Get default branch
```

### Configuration

```go
waitrose.Config{
    BaseURL:    "https://www.waitrose.com/api/graphql-prod/graph/live", // Default
    APIKey:     "your-api-key",      // Optional - see notes below
    UserAgent:  "Custom/1.0",        // Optional
    HTTPClient: &http.Client{},      // Optional
}
```

## Notes

### Authentication Headers

The Waitrose API uses **two separate authentication mechanisms**:

| Header | Purpose | Required |
|--------|---------|----------|
| `x-api-key` | API service access key | hard coded in APK |
| `Authorization: Bearer <token>` | User authentication | Yes, after login |


### Technical Details

- Reverse-engineered from Android app v3.9.1.14114
- GraphQL endpoint: `https://www.waitrose.com/api/graphql-prod/graph/live`

## Legal Disclaimer

This is an unofficial client created through reverse engineering for educational purposes. Use at your own risk and in compliance with Waitrose's terms of service.
