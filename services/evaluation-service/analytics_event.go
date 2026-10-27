package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
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
}

func (a *App) sendEvaluationEvent(ctx context.Context, userID, flagName string, result bool) {
	event := EvaluationEvent{
		UserID:    userID,
		FlagName:  flagName,
		Result:    result,
		Timestamp: time.Now().UTC(),
	}

	body, err := json.Marshal(event)
	if err != nil {
		slog.ErrorContext(ctx, "erro ao serializar evento de avaliação", "error", err)
		return
	}

	if a.EventPublisher == nil {
		slog.InfoContext(ctx, "[ANALYTICS_QUEUE_DISABLED] evento de avaliação", "event", string(body))
		return
	}

	// Span de produtor: o contexto dele segue nos metadados da mensagem até o analytics-service.
	ctx, span := otel.Tracer(serviceName).Start(ctx, "publish "+analyticsQueueName,
		trace.WithSpanKind(trace.SpanKindProducer),
		trace.WithAttributes(
			attribute.String("messaging.system", "oci_queue"),
			attribute.String("messaging.destination.name", analyticsQueueName),
			attribute.String("messaging.operation.type", "send"),
		),
	)
	defer span.End()

	if err := a.EventPublisher.Publish(ctx, string(body)); err != nil {
		span.RecordError(err)
		span.SetStatus(codes.Error, "falha ao publicar evento")
		slog.ErrorContext(ctx, "erro ao enviar evento para OCI Queue", "error", err)
		return
	}

	slog.InfoContext(ctx, "evento de avaliação enviado para OCI Queue", "flag_name", flagName)
}
