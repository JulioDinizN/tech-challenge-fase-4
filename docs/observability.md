# Observabilidade — ToggleMaster Fase 4

Este documento descreve a camada de observabilidade e resposta a incidentes adicionada sobre a base da Fase 3. As seções marcadas como pendentes serão preenchidas durante a implementação.

## Fluxo de telemetria

```text
Serviços instrumentados (OpenTelemetry SDK)
  -> OTLP -> OpenTelemetry Collector
       -> métricas -> Prometheus
       -> logs     -> Loki
       -> traces   -> APM (Datadog ou New Relic)
Grafana consulta Prometheus e Loki
```

O OTel Collector é o ponto central de recebimento, processamento e exportação. Os serviços não exportam diretamente para os backends.

## Componentes

| Componente | Responsabilidade | Local |
| --- | --- | --- |
| Prometheus | Métricas de infraestrutura e aplicações | Repositório GitOps |
| Loki | Logs centralizados dos contêineres | Repositório GitOps |
| Grafana | Dashboards e alertas | Repositório GitOps |
| OTel Collector | Recebimento e roteamento da telemetria | Repositório GitOps |
| Instrumentação | SDKs OpenTelemetry Go e Python | `services/` |
| Self-Healing | Reação automática aos alertas | `scripts/self-healing/` |

## Instrumentação dos serviços

| Serviço | Linguagem | Situação |
| --- | --- | --- |
| auth-service | Go | Pendente |
| evaluation-service | Go | Pendente |
| flag-service | Python/Flask | Pendente |
| targeting-service | Python/Flask | Pendente |
| analytics-service | Python | Pendente |

O evaluation-service chama flag e targeting por HTTP e publica eventos na OCI Queue consumidos pelo analytics-service. Para o mapa de serviços incluir o analytics-service, o contexto de trace precisa ser propagado na mensagem da fila.

## Alertas, incidentes e ChatOps

Pendente: regra de alerta, integração com a ferramenta de incidentes e canal de notificação.

## Self-Healing

Pendente: mecanismo de reação ao alerta. Ver [scripts/self-healing](../scripts/self-healing/README.md).
