package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/joho/godotenv"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// Contexto global para o Redis
var ctx = context.Background()

// App struct para injeção de dependência
type App struct {
	RedisClient         *redis.Client
	EventPublisher      AnalyticsEventPublisher
	HttpClient          *http.Client
	FlagServiceURL      string
	TargetingServiceURL string
}

func main() {
	_ = godotenv.Load() // Carrega .env para dev local

	shutdownTelemetry, err := setupTelemetry(ctx)
	if err != nil {
		log.Fatalf("Não foi possível configurar o OpenTelemetry: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := shutdownTelemetry(shutdownCtx); err != nil {
			log.Printf("Erro ao finalizar o OpenTelemetry: %v", err)
		}
	}()

	// --- Configuração ---
	port := os.Getenv("PORT")
	if port == "" {
		port = "8004"
	}

	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		log.Fatal("REDIS_URL deve ser definida (ex: redis://localhost:6379)")
	}

	flagSvcURL := os.Getenv("FLAG_SERVICE_URL")
	if flagSvcURL == "" {
		log.Fatal("FLAG_SERVICE_URL deve ser definida")
	}

	targetingSvcURL := os.Getenv("TARGETING_SERVICE_URL")
	if targetingSvcURL == "" {
		log.Fatal("TARGETING_SERVICE_URL deve ser definida")
	}

	// --- Inicializa Clientes ---

	// Cliente Redis
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		log.Fatalf("Não foi possível parsear a URL do Redis: %v", err)
	}
	rdb := redis.NewClient(opt)
	if _, err := rdb.Ping(ctx).Result(); err != nil {
		log.Fatalf("Não foi possível conectar ao Redis: %v", err)
	}
	log.Println("Conectado ao Redis com sucesso!")

	// Publicador OCI Queue. Sem OCI_QUEUE_OCID, o modo local apenas registra os eventos.
	eventPublisher, err := newAnalyticsEventPublisherFromEnv()
	if err != nil {
		log.Fatalf("Não foi possível inicializar o publicador OCI Queue: %v", err)
	}
	if eventPublisher == nil {
		log.Println("OCI Queue não configurada. Eventos de analytics serão registrados apenas no log.")
	} else {
		log.Println("Publicador OCI Queue inicializado com sucesso.")
	}

	// Cliente HTTP (com timeout) que propaga o contexto de trace para flag e targeting
	httpClient := &http.Client{
		Timeout:   5 * time.Second,
		Transport: otelhttp.NewTransport(http.DefaultTransport),
	}

	// Cria a instância da App
	app := &App{
		RedisClient:         rdb,
		EventPublisher:      eventPublisher,
		HttpClient:          httpClient,
		FlagServiceURL:      flagSvcURL,
		TargetingServiceURL: targetingSvcURL,
	}

	// --- Rotas ---
	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)
	mux.HandleFunc("/evaluate", app.evaluationHandler)

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           instrumentHandler(mux),
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("Serviço de Avaliação (Go) rodando na porta %s", port)
	if err := server.ListenAndServe(); err != nil {
		log.Print(err)
	}
}
