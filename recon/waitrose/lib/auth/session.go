package auth

import (
	"sync"
	"time"

	"github.com/jingkaihe/waitrose/models"
)

type Session struct {
	mu                 sync.RWMutex
	accessToken        string
	refreshToken       string
	customerID         string
	customerOrderID    string
	customerOrderState string
	defaultBranchID    string
	expiresAt          time.Time
}

func NewSession() *Session {
	return &Session{}
}

func (s *Session) Update(payload *models.SessionPayload) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.accessToken = payload.AccessToken
	s.refreshToken = payload.RefreshToken
	s.customerID = payload.CustomerID
	s.customerOrderID = payload.CustomerOrderID
	s.customerOrderState = payload.CustomerOrderState
	s.defaultBranchID = payload.DefaultBranchID
	s.expiresAt = time.Now().Add(time.Duration(payload.ExpiresIn) * time.Second)
}

func (s *Session) AccessToken() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.accessToken
}

func (s *Session) RefreshToken() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.refreshToken
}

func (s *Session) CustomerID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.customerID
}

func (s *Session) CustomerOrderID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.customerOrderID
}

func (s *Session) DefaultBranchID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.defaultBranchID
}

func (s *Session) ExpiresAt() time.Time {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.expiresAt
}

func (s *Session) IsExpired() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.isExpiredUnsafe()
}

func (s *Session) isExpiredUnsafe() bool {
	return time.Now().After(s.expiresAt.Add(-30 * time.Second))
}

func (s *Session) IsAuthenticated() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.accessToken != "" && !s.isExpiredUnsafe()
}

func (s *Session) Clear() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.accessToken = ""
	s.refreshToken = ""
	s.customerID = ""
	s.customerOrderID = ""
	s.customerOrderState = ""
	s.defaultBranchID = ""
	s.expiresAt = time.Time{}
}
