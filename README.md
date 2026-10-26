# POSTECH Tech Challenge — Fase 4

ToggleMaster: cinco microsserviços com infraestrutura Terraform, CI/DevSecOps no GitHub Actions e entrega por GitOps no OCI Kubernetes Engine (OKE). A Fase 4 adiciona observabilidade com OpenTelemetry, Prometheus, Loki e Grafana, APM com traces distribuídos, alertas com gestão de incidentes e ChatOps, e automação de Self-Healing.

## Repositórios e entrega

- [Código, infraestrutura e CI](https://github.com/JulioDinizN/tech-challenge-fase-4).
- [Estado desejado Kubernetes](https://github.com/JulioDinizN/tech-challenge-fase-4-gitops).
- [Documentação](docs/README.md), [observabilidade](docs/observability.md) e [relatório](docs/report.html).

## Fluxo de entrega

```text
Pull Request → detecção de serviços → testes → lint → SAST/SCA → build/scan
Push na main → mesmas validações → publicação da imagem escaneada no OCIR
             → commit com as tags no GitOps → reconciliação automática pelo Argo CD
```

Cada serviço utiliza um workflow reutilizável, selecionado por uma matriz de arquivos alterados. Mudanças compartilhadas selecionam os cinco serviços. PRs validam sem credenciais de publicação. Na main, toda a matriz precisa passar antes da publicação. Um único job reúne as tags em um commit GitOps.

O Terraform provisiona a infraestrutura a partir de uma execução autenticada com state remoto. Seu CI verifica formatação, configuração e segurança; não executa plan/apply. O CI de aplicações não aplica manifests no cluster.

## Estrutura

```text
.ci/                         # Catálogo de serviços e ferramentas
.github/workflows/           # Validação, publicação e promoção
services/                    # auth, flag, targeting, evaluation e analytics
docker/                      # Inicialização dos bancos de desenvolvimento
docker-compose.yml           # Ambiente local
infra/environments/homolog/  # Roots backend, core e platform
infra/modules/oci-runtime/   # Recursos OCI separados por responsabilidade
scripts/ci/                  # Detecção de alterações e promoção GitOps
scripts/self-healing/        # Automação de resposta aos alertas
scripts/                     # Bootstrap, verificações e geração dos documentos
docs/                        # Arquitetura, observabilidade, operação, decisões e relatório
```

Os manifests Kubernetes ficam exclusivamente no repositório GitOps. `backend`, `core` e `platform` representam responsabilidades com states separados de um único ambiente de homologação.

## Segurança e ativação

- Testes, lint, SAST/SCA e scan de imagem são bloqueantes. Trivy reprova achados CRITICAL.
- `ENABLE_OCIR_PUBLISH=true` permite publicar imagens somente em pushes na main.
- `ENABLE_GITOPS_PROMOTION=true` permite atualizar o GitOps após a publicação.
- OCI Vault fornece segredos de runtime via Workload Identity e Secrets Store CSI.
- Publicação recebe somente `OCIR_USERNAME` e `OCIR_AUTH_TOKEN`; promoção usa `GITOPS_SSH_KEY` com escrita restrita ao GitOps.
- Registry, namespace e prefixo OCIR são GitHub Variables não secretas.
- Arquivos reais de parâmetros, autenticação, state e planos salvos ficam fora do controle de versão. Modelos `.example` documentam a configuração.

## Desenvolvimento e operação

- [Desenvolvimento local](docs/local-development.md).
- [Validação, bootstrap e encerramento](docs/operations.md).
- [Catálogo de scripts](scripts/README.md).
- [Arquitetura e diagramas](docs/architecture.md).

Com os providers já inicializados e as dependências Python disponíveis:

```bash
PYTHON_BIN=/caminho/do/venv/bin/python ./scripts/validate.sh
```

A verificação local não publica imagens nem altera o cluster. O ambiente de demonstração não possui teardown automático; seu encerramento exige revisão dos recursos e dos states descritos no procedimento de operação.

## Proveniência

Este repositório evolui da Fase 3, commit `ccd8b7dbd66fe02561f87454442791d0d6681668` de `JulioDinizN/tech-challenge-fase-3`, preservando seu histórico. A stack de monitoramento, a instrumentação dos serviços e o Self-Healing são as adições da Fase 4.
