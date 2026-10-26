# Documentação — Fase 4

- [Arquitetura](architecture.md): Terraform, fluxo CI/GitOps e runtime OCI.
- [Observabilidade](observability.md): OpenTelemetry, métricas, logs, APM, alertas e Self-Healing.
- [Operação](operations.md): validação, bootstrap, acesso e encerramento.
- [Decisões](decisions/0001-repository-strategy.md): estratégia de repositórios, CI e segredos.
- [Desenvolvimento local](local-development.md): execução dos serviços com Docker Compose.
- [Scripts](../scripts/README.md): automação mantida nesta entrega.

## Diagramas

| Visão | Fonte editável | Exportação |
| --- | --- | --- |
| Infraestrutura e entrega | [Draw.io](diagrams/overall-architecture.drawio) | [PNG](diagrams/overall-architecture.png) |
| Runtime OCI | [Draw.io](diagrams/runtime-architecture.drawio) | [PNG](diagrams/runtime-architecture.png) |

As fontes `.drawio` são editáveis. `npm run diagrams:export` regenera os PNGs com draw.io Desktop; `DRAWIO_BIN` permite indicar outro caminho para o executável.

## Relatório

[HTML](report.html) é a fonte de impressão. `npm run report:pdf` gera `dist/delivery-report.pdf`, versionado junto com o HTML. O relatório incluirá o link do vídeo e as evidências exigidas pela Fase 4.
