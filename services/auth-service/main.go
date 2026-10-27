package main

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/XSAM/otelsql"
	_ "github.com/jackc/pgx/v4/stdlib"
	"github.com/joho/godotenv"
	semconv "go.opentelemetry.io/otel/semconv/v1.43.0"
	"go.opentelemetry.io/otel/trace"
)

// App struct (para injeção de dependência)
type App struct {
	DB        *sql.DB
	MasterKey string
}

func main() {
	// Carrega o .env para desenvolvimento local. Em produção, isso não fará nada.
	_ = godotenv.Load()

	shutdownTelemetry, err := setupTelemetry(context.Background())
	if err != nil {
		log.Fatalf("Não foi possível configurar o OpenTelemetry: %v", err)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := shutdownTelemetry(ctx); err != nil {
			log.Printf("Erro ao finalizar o OpenTelemetry: %v", err)
		}
	}()

	// --- Configuração ---
	port := os.Getenv("PORT")
	if port == "" {
		port = "8001" // Porta padrão
	}

	databaseURL, err := databaseDSN()
	if err != nil {
		log.Fatalf("Configuração do PostgreSQL inválida: %v", err)
	}

	masterKey := os.Getenv("MASTER_KEY")
	if masterKey == "" {
		log.Fatal("MASTER_KEY deve ser definida")
	}

	// --- Conexão com o Banco ---
	db, err := connectDB(databaseURL)
	if err != nil {
		log.Fatalf("Não foi possível conectar ao banco de dados: %v", err)
	}
	defer func() {
		if err := db.Close(); err != nil {
			log.Printf("Unable to close database: %v", err)
		}
	}()

	if err := bootstrapAPIKey(db); err != nil {
		log.Fatalf("Não foi possível criar a chave inicial da API: %v", err)
	}

	app := &App{
		DB:        db,
		MasterKey: masterKey,
	}
	faults := &faultInjector{enabled: os.Getenv("FAULT_INJECTION_ENABLED") == "true"}

	// --- Rotas da API ---
	mux := http.NewServeMux()
	mux.HandleFunc("/health", app.healthHandler)

	// Endpoint público para validar uma chave
	mux.HandleFunc("/validate", app.validateKeyHandler)

	// Endpoints de "admin" para criar/gerenciar chaves
	// Eles são protegidos pelo middleware de autenticação
	mux.Handle("/admin/keys", app.masterKeyAuthMiddleware(http.HandlerFunc(app.createKeyHandler)))

	// Injeção de falha para a demonstração de alerta e Self-Healing
	mux.Handle("/admin/fault", app.masterKeyAuthMiddleware(http.HandlerFunc(faults.handler)))

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           instrumentHandler(faults.middleware(mux)),
		ReadHeaderTimeout: 10 * time.Second,
	}

	log.Printf("Serviço de Autenticação (Go) rodando na porta %s", port)
	if err := server.ListenAndServe(); err != nil {
		log.Print(err)
	}
}

// connectDB inicializa e testa a conexão com o PostgreSQL
func connectDB(databaseURL string) (*sql.DB, error) {
	db, err := otelsql.Open("pgx", databaseURL,
		otelsql.WithAttributes(semconv.DBSystemNamePostgreSQL),
		otelsql.WithSpanOptions(otelsql.SpanOptions{
			OmitConnResetSession: true,
			OmitRows:             true,
			// Só cria spans de banco dentro de uma requisição rastreada.
			SpanFilter: func(ctx context.Context, _ otelsql.Method, _ string, _ []driver.NamedValue) bool {
				return trace.SpanContextFromContext(ctx).IsValid()
			},
		}),
	)
	if err != nil {
		return nil, err
	}

	if err = db.Ping(); err != nil {
		return nil, err
	}

	log.Println("Conectado ao PostgreSQL com sucesso!")
	return db, nil
}

func bootstrapAPIKey(db *sql.DB) error {
	bootstrapKey := os.Getenv("BOOTSTRAP_API_KEY")
	if bootstrapKey == "" {
		return nil
	}

	keyName := os.Getenv("BOOTSTRAP_API_KEY_NAME")
	if keyName == "" {
		keyName = "bootstrap-service-key"
	}

	_, err := db.Exec(
		"INSERT INTO api_keys (name, key_hash) VALUES ($1, $2) ON CONFLICT (key_hash) DO NOTHING",
		keyName,
		hashAPIKey(bootstrapKey),
	)
	if err != nil {
		return err
	}

	log.Printf("Chave inicial da API disponível (Name: %s)", keyName)
	return nil
}
