# Self-Healing

Automação de resposta a incidentes da Fase 4. Recebe o webhook do Grafana Alerting e executa o equivalente a `kubectl rollout restart deployment/<serviço>` no namespace `togglemaster`, sem intervenção humana.

Não é um microsserviço do ToggleMaster: não é instrumentado com OpenTelemetry e não aparece no Service Map. Fica no catálogo de CI para reutilizar testes, SAST, scan de imagem, publicação e promoção GitOps.

## Funcionamento

1. `POST /webhook` com `Authorization: Bearer <SELF_HEALING_TOKEN>`.
2. Para cada alerta em `firing`, lê o rótulo `deployment` (ou `service`) e confere `ALLOWED_DEPLOYMENTS`.
3. Aplica o patch `spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"]` pela API do Kubernetes, com a ServiceAccount do pod.
4. Cooldown por Deployment (`COOLDOWN_SECONDS`, padrão 300) evita reinícios em laço.
5. Alertas `resolved` e Deployments fora da allowlist são ignorados e registrados.

Cada ação gera uma linha JSON no stdout, usada como evidência:

```bash
kubectl logs deploy/self-healing -n togglemaster
```

## Configuração

| Variável | Descrição |
| --- | --- |
| `SELF_HEALING_TOKEN` | Token esperado no header `Authorization` (OCI Vault no cluster) |
| `ALLOWED_DEPLOYMENTS` | Lista separada por vírgulas |
| `TARGET_NAMESPACE` | Padrão `togglemaster` |
| `COOLDOWN_SECONDS` | Padrão `300` |
| `DRY_RUN` | `true` só registra a ação (Docker Compose) |
| `KUBERNETES_API_URL` | Padrão `https://kubernetes.default.svc` |

O RBAC (GitOps `apps/self-healing`) permite somente `get` e `patch` nos cinco Deployments da aplicação.

## Testes

```bash
python -m pytest -q services/self-healing
```

Os testes usam um servidor HTTP falso no lugar da API do Kubernetes.
