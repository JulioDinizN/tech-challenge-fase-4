package main

import (
	"context"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

type captureTransport func(*http.Request) (*http.Response, error)

func (f captureTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestFlagNamesCannotChangeServiceOrigin(t *testing.T) {
	for _, name := range []string{"normal", "//evil.invalid/path", "a?token=bad#frag", "../admin"} {
		t.Run(name, func(t *testing.T) {
			var observed *url.URL
			app := &App{FlagServiceURL: "http://flag-service:8002", TargetingServiceURL: "http://targeting-service:8003", HttpClient: &http.Client{Transport: captureTransport(func(r *http.Request) (*http.Response, error) {
				observed = r.URL
				return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{}`)), Header: make(http.Header)}, nil
			})}}
			if _, err := app.fetchFlag(context.Background(), name); err != nil {
				t.Fatal(err)
			}
			if observed.Host != "flag-service:8002" || observed.RawQuery != "" || observed.Fragment != "" {
				t.Fatalf("unsafe URL: %s", observed)
			}
			if observed.EscapedPath() != "/flags/"+url.PathEscape(name) {
				t.Fatalf("unexpected path: %s", observed)
			}
			if _, err := app.fetchRule(context.Background(), name); err != nil {
				t.Fatal(err)
			}
			if observed.Host != "targeting-service:8003" || observed.RawQuery != "" || observed.Fragment != "" {
				t.Fatalf("unsafe URL: %s", observed)
			}
		})
	}
}
