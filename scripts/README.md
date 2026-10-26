# Scripts da Fase 4

```text
scripts/
├── ci/           # Executados pelo GitHub Actions
├── ops/          # Bootstrap e verificações operacionais
├── docs/         # Geração dos diagramas e relatório
├── maintenance/  # Reprodução do chart versionado
├── tests/        # Testes da automação
└── validate.sh   # Entrada única de validação local
```

## CI — execução automática

| Script | Quem utiliza | Responsabilidade |
| --- | --- | --- |
| `ci/detect_changed_services.py` | Services CI | Seleciona a matriz a partir do diff Git |
| `ci/write_promotion.py` | Publicação de serviços | Gera o descritor da imagem publicada |
| `ci/promote_gitops.py` | Promoção GitOps | Atualiza as tags dos serviços selecionados |

A publicação pertence ao GitHub Actions, os add-ons ao Terraform platform e os workloads ao Argo CD.

## Operação — execução sob demanda

| Script | Quando utilizar | Efeito |
| --- | --- | --- |
| `ops/check-cloud-prerequisites.sh` | Antes de operar a infraestrutura | Verifica ferramentas instaladas |
| `ops/configure-gitops.py` | Bootstrap dos cinco serviços | Lê outputs de core e edita o checkout GitOps local, sem push ou deploy |
| `ops/smoke-oke.sh` | Verificação funcional pelo ingress | Cria/atualiza dados de demonstração |

O configurador é usado somente no bootstrap. Promoções posteriores são feitas pelo CI e preservam as tags dos serviços inalterados.

Com o kubeconfig privado selecionado, executar `./scripts/ops/smoke-oke.sh`. O script obtém a credencial de runtime sem imprimi-la e verifica autenticação, flag, regra e avaliação. Não habilitar shell tracing (`set -x`). Procedimentos em [operações](../docs/operations.md).

## Documentação e manutenção

- `docs/export-diagrams.mjs`: utilizado por `npm run diagrams:export` para exportar as fontes Draw.io.
- `docs/render-report-pdf.mjs`: utilizado por `npm run report:pdf` para gerar `dist/delivery-report.pdf`.
- `maintenance/vendor-nginx-chart.py`: utilizado ao reproduzir o chart NGINX versionado, com entradas de checksum fixado. Não faz parte de cada deploy; instruções no [README do chart](../infra/environments/homolog/platform/charts/README.md).

## Validação local

```bash
PYTHON_BIN=/caminho/do/venv/bin/python ./scripts/validate.sh
```

Executa os testes em `tests/`, formatação e validação dos roots Terraform já inicializados, validação da estrutura GitOps e do Compose. Não provisiona, publica, aplica manifests nem consulta o cluster.

Testes da automação isoladamente:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
```
