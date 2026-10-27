package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

const analyticsQueueName = "togglemaster-analytics"

type AnalyticsEventPublisher interface {
	Publish(ctx context.Context, content string) error
}

type EvaluationEvent struct {
	UserID    string    `json:"user_id"`
	FlagName  string    `json:"flag_name"`
	Result    bool      `json:"result"`
	Timestamp time.Time `json:"timestamp"`
	// TraceContext leva o traceparent W3C até o analytics-service, que continua o mesmo trace.
	TraceContext map[string]string `json:"trace_context,omitempty"`
}

func (a *App) sendEvaluationEvent(ctx context.Context, userID, flagName string, result bool) {
	event := EvaluationEvent{
		UserID:    userID,
		FlagName:  flagName,
		Result:    result,
		Timestamp: time.Now().UTC(),
	}

	if a.EventPublisher == nil {
		body, _ := json.Marshal(event)
		slog.InfoContext(ctx, "[ANALYTICS_QUEUE_DISABLED] evento de avaliação", "event", string(body))
		return
	}

	// Span de produtor: o contexto dele segue no corpo da mensagem até o analytics-service.
	ctx, span := otel.Tracer(serviceName).Start(ctx, "publish "+analyticsQueueName,
		trace.WithSpanKind(trace.SpanKindProducer),
		trace.WithAttributes(
			attribute.String("messaging.system", "oci_queue"),
			attribute.String("messaging.destination.name", analyticsQueueName),
			attribute.String("messaging.operation.type", "send"),
		),
	)
	defer span.End()

	event.TraceContext = traceProperties(ctx)
	body, err := json.Marshal(event)
	if err != nil {
		span.RecordError(err)
		slog.ErrorContext(ctx, "erro ao serializar evento de avaliação", "error", err)
		return
	}

	if err := a.EventPublisher.Publish(ctx, string(body)); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "falha ao publicar evento")
		slog.ErrorContext(ctx, "erro ao enviar evento para OCI Queue", "error", err)
		return
	}

	slog.InfoContext(ctx, "evento de avaliação enviado para OCI Queue", "flag_name", flagName)
}

// traceProperties serializa o contexto de trace atual (traceparent W3C).
// Fica no corpo da mensagem: os metadados da OCI Queue exigem um channelId,
// e o projeto não usa canais.
func traceProperties(ctx context.Context) map[string]string {
	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	return carrier
}
