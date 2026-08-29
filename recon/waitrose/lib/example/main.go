package main

import (
	"context"
	"fmt"
	"log"
	"os"

	waitrose "github.com/jingkaihe/waitrose"
	"github.com/jingkaihe/waitrose/models"
)

func main() {
	apiKey := os.Getenv("WAITROSE_API_KEY")
	if apiKey == "" {
		log.Fatal("WAITROSE_API_KEY environment variable is required")
	}

	client := waitrose.NewClient(waitrose.Config{
		APIKey: apiKey,
	})

	ctx := context.Background()

	username := os.Getenv("WAITROSE_USERNAME")
	password := os.Getenv("WAITROSE_PASSWORD")

	if username != "" && password != "" {
		session, err := client.Login(ctx, username, password)
		if err != nil {
			log.Fatalf("Login failed: %v", err)
		}
		fmt.Printf("Logged in as customer: %s\n", session.CustomerID)
		fmt.Printf("Access token expires in: %d seconds\n", session.ExpiresIn)

		trolley, err := client.GetTrolley(ctx)
		if err != nil {
			log.Fatalf("Failed to get trolley: %v", err)
		}
		fmt.Printf("Trolley has %d products\n", len(trolley.Products))
		if trolley.Trolley != nil && trolley.Trolley.TrolleyTotals != nil && trolley.Trolley.TrolleyTotals.TotalEstimatedCost != nil {
			fmt.Printf("Total: £%.2f\n", trolley.Trolley.TrolleyTotals.TotalEstimatedCost.Amount)
		}

		size := 5
		sortBy := "-"
		orders, err := client.GetOrders(ctx, models.GetOrdersInput{
			Size:   &size,
			SortBy: &sortBy,
		})
		if err != nil {
			log.Fatalf("Failed to get orders: %v", err)
		}
		if orders != nil {
			fmt.Printf("Found %d orders\n", len(orders.Content))
			for _, order := range orders.Content {
				fmt.Printf("  - Order %s: %s\n", order.CustomerOrderID, order.Status)
			}
		}

		if client.Session().IsExpired() {
			_, err := client.RefreshSession(ctx)
			if err != nil {
				log.Printf("Failed to refresh session: %v", err)
			} else {
				fmt.Println("Session refreshed successfully")
			}
		}

		if err := client.Logout(ctx); err != nil {
			log.Printf("Logout failed: %v", err)
		} else {
			fmt.Println("Logged out successfully")
		}
	} else {
		fmt.Println("No credentials provided, running in unauthenticated mode")
		fmt.Println("Set WAITROSE_USERNAME and WAITROSE_PASSWORD to authenticate")
	}
}
