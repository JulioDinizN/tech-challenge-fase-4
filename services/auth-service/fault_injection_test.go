package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFaultInjectionFailsRequestsButKeepsHealthy(t *testing.T) {
	faults := &faultInjector{enabled: true}
	faults.errorRate.Store(100)
	handler := faults.middleware(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	validate := httptest.NewRecorder()
	handler.ServeHTTP(validate, httptest.NewRequest(http.MethodGet, "/validate", nil))
	if validate.Code != http.StatusInternalServerError {
		t.Fatalf("/validate status = %d, want 500", validate.Code)
	}

	health := httptest.NewRecorder()
	handler.ServeHTTP(health, httptest.NewRequest(http.MethodGet, "/health", nil))
	if health.Code != http.StatusOK {
		t.Fatalf("/health status = %d, want 200", health.Code)
	}
}

func TestFaultInjectionHandler(t *testing.T) {
	tests := []struct {
		name     string
		enabled  bool
		body     string
		wantCode int
		wantRate int64
	}{
		{"disabled", false, `{"error_rate":50}`, http.StatusNotFound, 0},
		{"valid", true, `{"error_rate":50}`, http.StatusOK, 50},
		{"out of range", true, `{"error_rate":150}`, http.StatusBadRequest, 0},
		{"invalid json", true, `nope`, http.StatusBadRequest, 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			faults := &faultInjector{enabled: tt.enabled}
			rec := httptest.NewRecorder()
			faults.handler(rec, httptest.NewRequest(http.MethodPost, "/admin/fault", strings.NewReader(tt.body)))

			if rec.Code != tt.wantCode {
				t.Fatalf("status = %d, want %d", rec.Code, tt.wantCode)
			}
			if got := faults.errorRate.Load(); got != tt.wantRate {
				t.Fatalf("error rate = %d, want %d", got, tt.wantRate)
			}
		})
	}
}
