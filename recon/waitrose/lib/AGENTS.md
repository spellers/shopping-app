# AGENTS.md - Waitrose Go Client

## Project Overview

A Go client library and CLI for the Waitrose & Partners grocery API, reverse-engineered from the official Android app (v3.9.1.14114). Provides both a reusable library package and a command-line tool for interacting with Waitrose services.

See `README.md` for installation instructions, CLI usage, and library API reference.

## Project Structure

```
├── client.go           # Main library - all API methods (Login, GetTrolley, GetOrders, etc.)
├── cmd/waitrose/       # CLI application using Cobra
│   └── main.go         # All CLI commands and session persistence
├── auth/               # Session management
│   └── session.go      # Thread-safe session state with mutex
├── models/             # Data structures for API requests/responses
│   ├── session.go      # Authentication types
│   ├── trolley.go      # Shopping cart types
│   ├── slots.go        # Delivery slot types
│   ├── orders.go       # Order history types
│   ├── search.go       # Product search types
│   ├── products.go     # Product detail types
│   └── address.go      # Address types
├── graphql/            # GraphQL operation definitions
│   └── operations.go   # Raw GraphQL queries/mutations as const strings
├── example/            # Usage examples
└── internal/           # (Empty - reserved for internal utilities)
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Go 1.25 |
| CLI Framework | `github.com/spf13/cobra` |
| UUID Generation | `github.com/google/uuid` |
| API Protocol | GraphQL (primary) + REST (search, products, addresses, slot cancellation) |
| Module Path | `github.com/jingkaihe/waitrose` |

## Key Commands

All tools are managed via `mise.toml`. Run `mise install` to set up the environment.

```bash
# Build the CLI (outputs to ./bin/waitrose)
mise run build

# Run tests
mise run test

# Format code (using gofumpt - stricter than go fmt)
mise run format

# Lint code (runs go vet, golangci-lint, staticcheck)
mise run lint

# Install dependencies
mise run install

# Cross-compile for all platforms
mise run cross-build

# Create GitHub release
mise run release
```

### Direct tool commands (if needed)

```bash
go fmt ./...                      # Standard Go formatter
gofumpt -w .                      # Stricter formatter (preferred)
go vet ./...                      # Go vet
golangci-lint run                 # Comprehensive linter
staticcheck -checks=all ./...     # Static analysis
```

## Architecture

### Client Pattern
- Single `Client` struct in `client.go` holds HTTP client, configuration, and session
- All API methods are receivers on `*Client`
- Methods accept `context.Context` as first parameter for cancellation
- Internal `doRequest()` and `doRequestWithToken()` handle GraphQL requests

### API Endpoints
The client uses multiple backend endpoints:
- **GraphQL**: `https://www.waitrose.com/api/graphql-prod/graph/live` (authentication, trolley, slots, orders)
- **Content/Search**: `https://www.waitrose.com/api/content-prod/v2/cms/publish/productcontent/search`
- **Products**: `https://www.waitrose.com/api/products-prod/v1/products`
- **Addresses**: `https://www.waitrose.com/api/address-prod/v2/addresses`
- **Slot Orchestration**: `https://www.waitrose.com/api/slot-orchestration-prod/v1`

### Session Management
- `auth.Session` is thread-safe (uses `sync.RWMutex`)
- CLI persists sessions to `~/.waitrose/session.json`
- Auto-refresh handled in CLI's `PersistentPreRunE`

## Conventions and Style

### Struct Definitions
- Use JSON tags with `omitempty` for optional fields
- Use pointers for truly optional fields that may be nil:
  ```go
  type SlotDaysInput struct {
      BranchID string  `json:"branchId,omitempty"`
      Size     *int    `json:"size,omitempty"`      // Optional pointer
  }
  ```

### Error Handling
- Wrap errors with context using `fmt.Errorf` and `%w`:
  ```go
  return fmt.Errorf("marshal request: %w", err)
  ```
- Check GraphQL response errors before data:
  ```go
  if len(resp.Errors) > 0 {
      return nil, fmt.Errorf("graphql error: %s", resp.Errors[0].Message)
  }
  ```

### API Method Pattern
```go
func (c *Client) MethodName(ctx context.Context, input InputType) (*OutputType, error) {
    variables := map[string]interface{}{
        "inputKey": input,
    }
    var resp ResponseType
    if err := c.doRequest(ctx, graphql.QueryConst, variables, &resp); err != nil {
        return nil, err
    }
    // Check errors, return data
}
```

### GraphQL Operations
- Stored as `const` strings in `graphql/operations.go`
- Named with suffix `Query` or `Mutation`
- Include `__typename` and `failures { type message }` in responses

### CLI Commands
- Use Cobra's command structure
- Support `--json` / `-j` flag for JSON output
- Check `client.Session().IsAuthenticated()` before authenticated operations
- Use 30-second timeouts with `context.WithTimeout`

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Input types | `*Input` suffix | `SlotDaysInput`, `BookSlotInput` |
| Response wrappers | `*Response` suffix | `SlotDaysResponse`, `GetOrdersResponse` |
| Response data | `*Data` suffix | `SlotDaysData`, `GetOrdersData` |
| Failure types | `*Failure` suffix | `SessionFailure`, `TrolleyFailure` |

### Helper Functions
- `deref(s *string) string` - Safely dereference string pointers
- `derefInt(i *int) int` - Safely dereference int pointers

## Testing

No tests exist currently. When adding tests:
- Use table-driven tests
- Mock HTTP responses for API testing
- Place test files alongside source files (`*_test.go`)

## Dependencies

Managed via Go modules (`go.mod`):
- Direct: `github.com/google/uuid`, `github.com/spf13/cobra`
- Indirect: `github.com/inconshreveable/mousetrap`, `github.com/spf13/pflag`

Run `go mod tidy` after adding/removing imports.

## Notes

- API key defaults to the production key extracted from the Android app
- Session tokens are JWTs; the CLI extracts expiry from the token payload
- Some endpoints require specific headers: `x-api-key`, `breadcrumb`, `client-correlation-id`
- Delivery slot operations require an `addressId` for delivery type slots
