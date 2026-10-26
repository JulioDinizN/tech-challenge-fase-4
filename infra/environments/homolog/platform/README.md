# Platform — Fase 4

Root Helm com CSI, provider OCI, Metrics Server, NGINX Ingress e Argo CD. Usa kubeconfig e contexto explícitos; não lê state/credenciais do core automaticamente. Entradas de rede são outputs não secretos do core. Backend remoto usa platform.tfstate.

`bootstrap_gitops=false` por padrão. Ativá-lo somente após imagens publicadas, inputs GitOps revisados e pull secret criado. A aplicação raiz é sincronizada manualmente no bootstrap; auto-sync dos serviços é ativado depois no GitOps. Sequência completa em `docs/operations.md`. Cada release deve ter um único proprietário; workloads são reconciliados pelo Argo CD.
