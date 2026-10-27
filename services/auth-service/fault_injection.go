package main

import (
	"encoding/json"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"sync/atomic"
)

// faultInjector simula uma falha que só desaparece quando o processo reinicia.
// Existe para demonstrar alerta e Self-Healing; fica desligado sem FAULT_INJECTION_ENABLED=true.
type faultInjector struct {
	enabled   bool
	errorRate atomic.Int64 // percentual de 0 a 100
}

type faultRequest struct {
	ErrorRate int `json:"error_rate"`
}

// middleware falha a fração configurada das requisições, exceto /health,
// para que as sondas do Kubernetes não reiniciem o pod antes da automação.
func (f *faultInjector) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rate := f.errorRate.Load()
		// #nosec G404 -- amostragem de falha simulada, sem uso criptográfico.
		if rate > 0 && r.URL.Path != "/health" && rand.Int64N(100) < rate {
			slog.ErrorContext(r.Context(), "falha injetada", "path", r.URL.Path, "error_rate", rate)
			http.Error(w, "Falha injetada para demonstração", http.StatusInternalServerError)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// handler ativa ou desativa a falha. Protegido pela MASTER_KEY no roteamento.
func (f *faultInjector) handler(w http.ResponseWriter, r *http.Request) {
	if !f.enabled {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "Método não permitido", http.StatusMethodNotAllowed)
		return
	}

	var req faultRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.ErrorRate < 0 || req.ErrorRate > 100 {
		http.Error(w, "error_rate deve estar entre 0 e 100", http.StatusBadRequest)
		return
	}

	f.errorRate.Store(int64(req.ErrorRate))
	slog.WarnContext(r.Context(), "injeção de falha atualizada", "error_rate", req.ErrorRate)
	writeJSON(w, map[string]int{"error_rate": req.ErrorRate})
}
