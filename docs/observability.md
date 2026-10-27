# Observabilidade — ToggleMaster Fase 4

Camada de observabilidade e resposta a incidentes adicionada sobre a base da Fase 3: instrumentação OpenTelemetry nos cinco serviços, OpenTelemetry Collector como peça central, Prometheus, Loki e Grafana no cluster, New Relic como APM, alerta com PagerDuty e Discord, e Self-Healing automático.

## Fluxo de telemetria

```text
auth · evaluation (Go, SDK OpenTelemetry)          ┐
flag · targeting · analytics (Python, auto-instr.) ┘── OTLP/HTTP ──▶ OpenTelemetry Collector (DaemonSet)
                                                                        │  + file_log: logs de todos os contêineres
                                                                        │  + k8s_attributes: namespace, pod, nó
                                                                        ├─ métricas ─▶ Prometheus (remote write)
                                                                        ├─ logs ─────▶ Loki (OTLP nativo)
                                                                        └─ traces ───▶ New Relic (OTLP)
Grafana ◀── Prometheus + Loki: dashboard, Explore e Grafana Alerting
Grafana Alerting ──▶ PagerDuty (incidente) · Discord (ChatOps) · Self-Healing (rollout restart)
```

Os serviços só conhecem o endpoint OTLP do Collector (`OTEL_EXPORTER_OTLP_ENDPOINT`). Trocar de backend, inclusive de APM, muda apenas a configuração do Collector.

## Componentes

| Componente | Função | Onde está |
| --- | --- | --- |
| OpenTelemetry Collector | Recebe OTLP, coleta logs dos nós, enriquece com metadados do Kubernetes e roteia | GitOps `observability/values/opentelemetry-collector.yaml` |
| Prometheus | Armazena métricas das aplicações (remote write) e do cluster (kubelet, node-exporter, kube-state-metrics) | GitOps `observability/values/kube-prometheus-stack.yaml` |
| Loki | Logs centralizados de todos os contêineres | GitOps `observability/values/loki.yaml` |
| Grafana | Dashboard, Explore e alertas; carregados por sidecars a partir de ConfigMaps | GitOps `observability/config/grafana/` |
| New Relic | APM: Distributed Tracing e Service Map | Exporter OTLP do Collector |
| PagerDuty | Incidente automático (Events API v2) | Contact point do Grafana |
| Discord | Notificação detalhada (ChatOps) | Contact point do Grafana |
| Self-Healing | Recebe o webhook do alerta e reinicia o Deployment | `services/self-healing/` e GitOps `apps/self-healing/` |

Todos os charts são Applications do Argo CD com versões fixas, no projeto `observability`. Credenciais vêm do OCI Vault por Workload Identity e Secrets Store CSI; o Git contém somente nomes de segredos.

## Instrumentação dos serviços

| Serviço | Linguagem | Como | Sinais |
| --- | --- | --- | --- |
| auth-service | Go | SDK + `otelhttp` + `otelsql` (`telemetry.go`) | traces, métricas HTTP/DB, logs (`slog` → OTLP) |
| evaluation-service | Go | SDK + `otelhttp` no servidor e no cliente HTTP; span de produtor na fila | traces, métricas HTTP, logs |
| flag-service | Python/Flask | `opentelemetry-instrument` no Dockerfile (Flask, requests, psycopg2, logging) | traces, métricas HTTP/DB, logs |
| targeting-service | Python/Flask | Igual ao flag-service | traces, métricas HTTP/DB, logs |
| analytics-service | Python | `opentelemetry-instrument` + span de consumidor manual na leitura da OCI Queue | traces, logs |

Detalhes relevantes:

- **Propagação W3C (`traceparent`).** O evaluation-service propaga o contexto nas chamadas HTTP para flag e targeting; estes propagam para o auth-service.
- **Fila.** O evaluation-service grava o `traceparent` no campo `trace_context` do evento publicado na OCI Queue (os metadados da fila exigem `channelId`, recurso que o projeto não usa). O analytics-service extrai esse contexto e cria o span `process togglemaster-analytics`, continuando o mesmo trace. Assim o Service Map mostra os cinco serviços.
- **Métricas HTTP.** Go e Python emitem `http.server.request.duration` (convenção estável; Python com `OTEL_SEMCONV_STABILITY_OPT_IN=http`). No Prometheus: `http_server_request_duration_seconds_{count,sum,bucket}`, com o serviço no rótulo `job`.
- **Logs com trace.** Logs emitidos durante uma requisição carregam `trace_id` e `span_id`. Os logs dos cinco serviços chegam por OTLP; os demais contêineres do cluster são lidos pelo `file_log` do Collector, que exclui os cinco serviços para não duplicar.
- **`/health` não é rastreado**, para que as sondas do Kubernetes não poluam traces e taxas.
- **psycopg2.** O `RealDictCursor` é definido no pool de conexões (e não em cada cursor) porque a instrumentação só rastreia cursores criados com a fábrica da conexão.

## Dashboard

`ToggleMaster — Saúde do Ecossistema` (`observability/config/grafana/dashboards/togglemaster-overview.json`), com filtro por serviço:

1. **Microsserviços:** requisições/s, % de 5xx, latência p95, 5xx do auth-service (mesma expressão do alerta), séries por serviço e por status HTTP.
2. **Recursos do cluster:** CPU e memória dos nós, CPU e memória por pod, réplicas do HPA, reinícios de contêiner.
3. **Logs em tempo real:** logs dos serviços e um painel só com erros e avisos.

## Alerta, incidente e ChatOps

Regra `AuthService5xxErrorRate` (`observability/config/grafana/alerting/togglemaster-rules.yaml`):

```promql
100 * (sum(rate(http_server_request_duration_seconds_count{job="auth-service", http_response_status_code=~"5.."}[1m])) or vector(0))
    / sum(rate(http_server_request_duration_seconds_count{job="auth-service"}[1m]))  > 5   por 1 minuto
```

Avaliada a cada 10 s; `noDataState: OK`. Rótulos `severity=critical`, `service=auth-service` e `deployment=auth-service`.

A política de notificação envia para o contact point `togglemaster-incidents`, com três integrações:

| Integração | Efeito |
| --- | --- |
| PagerDuty (Events API v2) | Abre o incidente no `Firing` e resolve no `Resolved` |
| Discord | Mensagem com serviço, severidade, valor medido, descrição, horário, dashboard e runbook |
| Webhook Self-Healing | Dispara o rollout restart do Deployment do rótulo `deployment` |

`repeat_interval: 4h` evita notificações (e reinícios) repetidos enquanto o alerta continua ativo.

## Self-Healing

`services/self-healing/app.py`, somente biblioteca padrão do Python:

1. Recebe `POST /webhook` do Grafana com `Authorization: Bearer <token>` (token gerado no Vault).
2. Para cada alerta em `firing`, lê o rótulo `deployment` e confere a allowlist (`ALLOWED_DEPLOYMENTS`).
3. Aplica o mesmo patch de `kubectl rollout restart`: anotação `kubectl.kubernetes.io/restartedAt` no template do pod, via API do Kubernetes com a ServiceAccount do pod.
4. Registra cada ação em JSON (`kubectl logs deploy/self-healing -n togglemaster`).
5. Aplica cooldown de 5 minutos por Deployment para não entrar em laço.

O Role `self-healing` só permite `get` e `patch` nos cinco Deployments listados em `resourceNames`; não pode apagar nem alterar nada além disso. Alertas `resolved` são ignorados.

### Runbook: auth-service 5xx

1. Abrir o dashboard pelo link da notificação e confirmar a taxa de 5xx e o impacto em flag/targeting/evaluation.
2. No Loki: `{service_name="auth-service"} | severity_text="ERROR"`; abrir o `trace_id` de uma linha no New Relic.
3. Conferir a ação automática: `kubectl logs deploy/self-healing -n togglemaster` e `kubectl rollout history deployment/auth-service -n togglemaster`.
4. Se a taxa não voltar ao normal em 5 minutos, o problema não é de estado do processo: investigar banco (`db_client_operation_duration_seconds`) e dependências. O cooldown impede um segundo reinício automático nesse intervalo.

### Falha injetada para a demonstração

O auth-service aceita `POST /admin/fault` (protegido pela MASTER_KEY) somente quando `FAULT_INJECTION_ENABLED=true`. O percentual configurado fica na memória do processo, portanto **só desaparece quando o pod reinicia**: é exatamente o tipo de falha que o Self-Healing corrige. `/health` nunca falha, para que o kubelet não reinicie o pod antes da automação.

```bash
curl -X POST "$AUTH_URL/admin/fault" -H "Authorization: Bearer $MASTER_KEY" -d '{"error_rate":60}'
```

A falha vale por pod; com mais de uma réplica, chamar cada pod (ou usar `error_rate` alto).

## Execução local

O Docker Compose sobe os serviços instrumentados, o Collector, Prometheus, Loki, Grafana, Jaeger (traces locais), um receptor que simula PagerDuty/Discord e o Self-Healing em `DRY_RUN`. Dashboard e regra de alerta são lidos do repositório GitOps (fonte única). Ver [desenvolvimento local](local-development.md#observabilidade-local).

Limites do ambiente local:

- Sem OCI Queue, o evaluation-service só registra os eventos em log; a aresta evaluation → analytics só aparece no cluster.
- Sem Kubernetes, o Self-Healing só registra o reinício (`DRY_RUN`); o reinício real foi validado em um cluster kind com os manifests do GitOps.
- Os painéis de recursos do cluster dependem de kubelet, node-exporter e kube-state-metrics e ficam vazios no Compose.

## Decisões

- **OpenTelemetry Collector como peça central** (obrigatório): serviços independentes de fornecedor; o Collector adiciona metadados do Kubernetes e coleta os logs dos nós.
- **New Relic como APM:** recebe OTLP nativamente, sem agente proprietário; o Service Map e o Distributed Tracing são gerados a partir dos spans OpenTelemetry. O Datadog exigiria exporter e conector específicos para o mapa de serviços.
- **PagerDuty para incidentes:** integração nativa com o Grafana Alerting, abertura e resolução automáticas. A Atlassian está descontinuando o OpsGenie e não aceita novos cadastros.
- **Grafana Alerting como origem do alerta:** uma única regra versionada aciona incidente, ChatOps e Self-Healing; o Alertmanager do kube-prometheus-stack fica desligado.
- **Self-Healing dentro do cluster:** a API do OKE aceita somente os CIDRs autorizados, portanto um runner hospedado do GitHub não alcançaria o cluster. O receptor interno usa RBAC mínimo e não expõe credenciais do cluster fora dele.
