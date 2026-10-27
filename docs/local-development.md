# Local Development

## Start The Stack

```bash
cp .env.example .env
docker compose up --build
```

For detached execution:

```bash
docker compose up -d --build
docker compose ps
```

Expected local shape (além da stack de observabilidade descrita em [Observabilidade local](#observabilidade-local)):

- 5 application containers:
  - `auth-service`
  - `flag-service`
  - `targeting-service`
  - `evaluation-service`
  - `analytics-service`
- 4 dependency containers:
  - `auth-db`
  - `app-db`
  - `redis`
  - `dynamodb-local`

## Local Ports

| Component | URL |
| --- | --- |
| auth-service | http://localhost:8001 |
| flag-service | http://localhost:8002 |
| targeting-service | http://localhost:8003 |
| evaluation-service | http://localhost:8004 |
| analytics-service | http://localhost:8005 |
| DynamoDB Local | http://localhost:8000 |
| auth-db PostgreSQL | localhost:5433 |
| app-db PostgreSQL | localhost:5434 |
| Redis | localhost:6379 |

## Health Checks

If direct host curls are available:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
```

If host networking is restricted, verify through Compose:

```bash
docker compose exec -T auth-service wget -qO- http://localhost:8001/health
docker compose exec -T flag-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8002/health', timeout=3).read().decode())"
docker compose exec -T targeting-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8003/health', timeout=3).read().decode())"
docker compose exec -T evaluation-service wget -qO- http://localhost:8004/health
docker compose exec -T analytics-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8005/health', timeout=3).read().decode())"
```

## Smoke Test

The local Compose stack seeds the API key from `.env.example`:

```text
tm_key_local_development_only
```

Run this from the repository root:

```bash
docker compose exec -T flag-service python - <<'PY'
import requests

api_key = 'tm_key_local_development_only'
headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
flag_name = 'enable-compose-demo'

validate = requests.get('http://auth-service:8001/validate', headers={'Authorization': f'Bearer {api_key}'}, timeout=5)
print('auth validate', validate.status_code, validate.text.strip())

flag_payload = {'name': flag_name, 'description': 'Docker Compose smoke test flag', 'is_enabled': True}
flag = requests.post('http://localhost:8002/flags', json=flag_payload, headers=headers, timeout=5)
if flag.status_code == 409:
    flag = requests.put(f'http://localhost:8002/flags/{flag_name}', json={'description': flag_payload['description'], 'is_enabled': True}, headers=headers, timeout=5)
print('flag upsert', flag.status_code, flag.text.strip())

rule_payload = {'flag_name': flag_name, 'is_enabled': True, 'rules': {'type': 'PERCENTAGE', 'value': 100}}
rule = requests.post('http://targeting-service:8003/rules', json=rule_payload, headers=headers, timeout=5)
if rule.status_code == 409:
    rule = requests.put(f'http://targeting-service:8003/rules/{flag_name}', json={'is_enabled': True, 'rules': rule_payload['rules']}, headers=headers, timeout=5)
print('rule upsert', rule.status_code, rule.text.strip())

evaluation = requests.get(f'http://evaluation-service:8004/evaluate?user_id=compose-user&flag_name={flag_name}', timeout=5)
print('evaluation', evaluation.status_code, evaluation.text.strip())
PY
```

Expected result:

- API key validates with status `200`.
- Flag create/update succeeds.
- Targeting rule create/update succeeds.
- Evaluation returns status `200` with `"result": true`.

## Local Analytics Note

`evaluation-service` leaves its OCI Queue publisher disabled when `OCI_QUEUE_OCID` is absent. It still evaluates flags and records the analytics event in its log.

`analytics-service` runs locally with `ANALYTICS_WORKER_ENABLED=false`, so its health endpoint remains available without OCI credentials or a local Queue emulator. The worker is enabled only in OKE. DynamoDB Local remains in Compose to preserve the nine-container shape requested by the challenge, but the OCI-adapted analytics worker does not write to it.

## Compatibilidade da configuração PostgreSQL

O Compose continua fornecendo `DATABASE_URL` para auth, flag e targeting. Ela tem prioridade, portanto nenhuma credencial OCI ou mudança no `.env` é necessária para desenvolvimento local.

Somente no OKE os serviços usam componentes separados:

```env
DB_HOST=<endpoint-privado>
DB_PORT=5432
DB_NAME=<banco-do-servico>
DB_USER=<usuario-restrito>
DB_PASSWORD=<Secret-sincronizado-do-Vault>
DB_SSLMODE=require
```

Esse contrato evita colocar senha em ConfigMap/Terraform e mantém o mesmo código executável nos dois ambientes.

## Observabilidade local

O mesmo `docker compose up -d --build` sobe a stack da Fase 4. Dashboard e regra de alerta são montados a partir do repositório GitOps vizinho (`GITOPS_ROOT`, padrão `../tech-challenge-fase-4-gitops`).

| Componente | URL |
| --- | --- |
| Grafana (admin/admin) | http://localhost:3000 |
| Prometheus | http://localhost:9090 (`PROMETHEUS_PORT` muda a porta do host) |
| Loki | http://localhost:3100 |
| Jaeger (traces locais) | http://localhost:16686 |
| OTel Collector (OTLP) | localhost:4317 (gRPC) e localhost:4318 (HTTP) |
| Self-Healing (`DRY_RUN`) | http://localhost:8080/health |

Gerar tráfego contínuo (cria a flag `demo-flag` e chama evaluation, flag e targeting):

```bash
python3 scripts/ops/generate-traffic.py --duration 300
```

Ensaiar o incidente: injetar erro no auth-service, aguardar cerca de 1 minuto em `Pending` e mais 1 minuto até `Firing` no Grafana Alerting, conferir a notificação no simulador e a ação do Self-Healing:

```bash
curl -X POST http://localhost:8001/admin/fault -H "Authorization: Bearer admin-secreto-123" -d '{"error_rate":60}'
docker compose logs -f self-healing webhook-sink
```

No Compose o Self-Healing roda em `DRY_RUN` e apenas registra o reinício. Para concluir o ensaio, reiniciar manualmente (`docker compose restart auth-service`) e acompanhar o alerta voltar a `Normal`.

Enviar os traces locais também ao New Relic (requer `NEW_RELIC_LICENSE_KEY` no `.env`):

```bash
docker compose -f docker-compose.yml -f docker-compose.newrelic.yml up -d otel-collector
```

Sem OCI Queue, a aresta evaluation → analytics não aparece localmente; ela depende do cluster.
