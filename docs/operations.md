# Operação — Fase 4

O Terraform gerencia a infraestrutura e os add-ons. GitHub Actions publica imagens e promove tags; Argo CD reconcilia os workloads. Operações de provisionamento e encerramento devem usar exclusivamente os roots de homologação descritos abaixo.

## Validação sem provisionamento

Instalar ferramentas Terraform, kubectl, Python e Docker CLI. Criar um venv e instalar `../tech-challenge-fase-4-gitops/scripts/requirements.txt` nele. Em uma cópia isolada para validação, inicializar os roots com `terraform -chdir=infra/environments/homolog/<root> init -backend=false -input=false`; isso baixa providers, sem configurar state remoto. Não executar esse init sobre um diretório de operação já configurado com backend remoto. Em checkouts de operação, manter o backend existente. Em seguida:

```bash
PYTHON_BIN=/caminho/do/venv/bin/python ./scripts/validate.sh
```

O script não faz plan, apply, deploy, push ou consultas ao cluster. Scans/testes dos serviços e build/scan das imagens são verificações adicionais do CI. Docker daemon é necessário para build de imagens, mas não para renderizar Compose.

## Propriedade Terraform

- `backend`: bucket privado/versionado e protegido contra destruição. Ver seu README para criação do bucket, init remoto e import.
- `core`: compõe `modules/oci-runtime`; contém a infraestrutura OCI, com outputs não secretos.
- `platform`: Helm gerencia CSI, provider OCI, Metrics Server, NGINX Ingress e Argo. API Argo permanece ClusterIP, acessada por port-forward.

Core exige região, OCIDs, IP permitido, versão Kubernetes e imagem OKE compatível. O exemplo usa Ashburn, workers E3 em AD-3 e PostgreSQL E5/E6/Standard3. A imagem foi validada no preflight; reconfirmar disponibilidade e quotas antes do apply. O ambiente usa PostgreSQL E5 para auth, E6 para flag e Standard3 para targeting, conforme cotas por shape. Core e platform usam chaves distintas do backend. Não versionar `.tfvars`, `backend.hcl`, kubeconfig, state ou planos salvos.

## Validação dos workers antes do deploy

Na Fase 2, a imagem OKE build `1505` falhou no initramfs com erro de resolução iSCSI, antes de cloud-init e kubelet. O `RegisterTimeOut` foi consequência; rede e criptografia PV em trânsito não eram a causa. A build `1462` funcionou em E3/AD-3, mas não consta no catálogo atual filtrado para OKE 1.34.2/OL8/x86.

Para esta implantação, reutilizar a combinação da Fase 2: Oracle Linux 8.10 build `1462`, Kubernetes `v1.34.2`, `VM.Standard.E3.Flex`, AD-3. O OCID exato continua `AVAILABLE` e compatível com E3, embora não esteja na lista atual de sugestões OKE. O preflight aceita uma imagem fixada fora dessa lista somente quando pertence ao mesmo compartimento de publicação da imagem oficial do catálogo e seu nome contém a versão Kubernetes solicitada. Também valida disponibilidade, shape e tamanho mínimo do disco pela API OCI.

Iniciar com um worker, aguardar `Ready`, conferir `status.nodeInfo.kubeletVersion` e testar agendamento antes de ampliar para dois. Se o registro falhar, investigar Work Request e console serial antes de repetir a criação. Compatibilidade declarada não substitui a verificação real de boot.

O primeiro boot da build `1578` completou initramfs/cloud-init, mas revelou um segundo problema: o kubelet rejeita `app.kubernetes.io/part-of` em `--node-labels`. O módulo usa agora o label inicial `project=togglemaster`, fora dos domínios reservados. Labels `app.kubernetes.io/*` dos manifests dos aplicativos não são afetados.

## Bootstrap de um novo ambiente

1. Aceitação OCI confirmada pelo responsável em 13/09/2026. Confirmar quotas, shapes, imagem/Kubernetes, orçamento e ausência de propriedade duplicada. Preparar bucket privado/versionado; verificar state remoto dos roots.
2. Revisar `core plan` e então provisionar. Criar kubeconfig no caminho privado e confirmar seu contexto. Preencher `platform/terraform.tfvars` com outputs de rede do core e o contexto explícito; `bootstrap_gitops=false` inicialmente.
3. Revisar e provisionar platform. Os workloads são gerenciados pelo Argo CD. Se charts já existirem, importar releases antes de aplicar, evitando dois donos.
4. Configurar GitHub Variables `OCIR_REGISTRY`, `OCIR_NAMESPACE`, `OCIR_REPOSITORY_PREFIX`; o prefixo deve ser o `project_name` do core. Secrets de publicação: OCIR_USERNAME, OCIR_AUTH_TOKEN e GITOPS_SSH_KEY (chave de deploy com escrita restrita ao GitOps). Nenhuma senha de aplicação vai ao CI. Segurança é obrigatória e independe de SECURITY_GATE_ENABLED.
5. Publicar uma base dos cinco serviços a partir de um push na main com alteração compartilhada revisada e `ENABLE_OCIR_PUBLISH=true`, mantendo `ENABLE_GITOPS_PROMOTION=false` nesta primeira publicação. `workflow_dispatch` valida, mas não publica. Verificar imagem/digest de cada serviço. Não usar push manual de imagem como evidência de CI.
6. Após as cinco imagens existirem, preencher GitOps localmente:

   ```bash
   python3 scripts/ops/configure-gitops.py \
     --gitops-root ../tech-challenge-fase-4-gitops \
     --initial-image-tag sha-<12-hex-do-push>
   python3 ../tech-challenge-fase-4-gitops/scripts/validate_structure.py --ready
   ```

   Esse comando lê apenas outputs conhecidos do core, substitui identificadores não secretos e as cinco tags iniciais; não aplica nem publica. Usá-lo somente no bootstrap, pois altera as tags dos cinco serviços. Revisar o diff antes de publicar. Promoções seguintes usam `promote_gitops.py` e preservam tags dos serviços inalterados.
7. Criar o pull secret `ocir-pull-secret` no namespace `togglemaster` por canal privado, antes de iniciar workloads. Seu valor não pertence ao Git. Argo precisa de credencial de leitura se o repositório GitOps for privado.
8. Após entradas revisadas no GitOps, habilitar `bootstrap_gitops=true` em platform. Sincronizar a aplicação raiz uma vez para criar AppProject, ApplicationSet e Application da plataforma. Sincronizar **primeiro** `togglemaster-platform` e esperar os três Jobs de banco concluírem. Namespace/config compartilhados pertencem somente a essa aplicação. Jobs são hooks Sync com limpeza após sucesso; inicialização é idempotente.
9. Sincronizar os cinco serviços inicialmente e conferir saúde. Depois ativar `automated.enabled: true` no ApplicationSet e na aplicação de plataforma mediante diff revisado. Atualizar a raiz para propagar essa política. Ativar `DEPLOYMENT_READY=true` no CI GitOps e `ENABLE_GITOPS_PROMOTION=true` no principal. A raiz é bootstrap manual; os cinco serviços precisam auto-sync para a demonstração.
10. Ensaiar PR vermelho → correção → merge → scan/publicação → commit GitOps → sync automático. Validar imagem/digest e smoke. O smoke altera dados de demonstração; executá-lo somente nessa janela.

Não mostrar conteúdo de Secrets/state/tfvars. A revisão de prontidão deve distinguir arquivos preparados de valores e comportamento confirmados no ambiente real.

## Encerramento

Após salvar/revisar evidências: interromper promoções e desativar auto-sync, remover workloads/controladores na ordem revisada, esperar remoção do Service LoadBalancer e recursos de rede gerados por Kubernetes, encerrar platform e só então core. O bucket de state é protegido e permanece. Se a remoção do NGINX via Helm deixar o LB em término, esperar a limpeza antes de destruir subnets/NSGs. Plan de destruição, retenção de dados/backups e custos remanescentes precisam de revisão específica futura.

## Janela de gravação e retenção

Usar somente homolog. Antes de criar cluster/bancos, aprovar CI remoto dos cinco serviços, build/scan das imagens, fixture de segurança e configuração de captura. Na janela autorizada, provisionar, validar, registrar IaC/CI/GitOps/Argo e conferir os clipes. Encerrar recursos assim que as evidências essenciais estiverem salvas; edição e upload não precisam do ambiente ligado. Se um bloqueio exigir trabalho fora da sessão acompanhada, salvar o diagnóstico e encerrar ordenadamente, sem deixar recursos durante a noite.

Verificar no encerramento recursos gerados pelo Kubernetes, volumes, backups, imagens/objetos retidos e exclusões pendentes. O bucket tem prevent_destroy e é retido por padrão. Não prometer custo zero enquanto houver itens residuais; registrar o inventário final. Nenhuma rotina automática de destruição está habilitada.

## Permissões a conferir antes de criar PostgreSQL

Além das quotas, conferir a identidade que executará Terraform: permissões de gerenciamento PostgreSQL/rede e leitura de `secret-family` e `vaults`, conforme a [política oficial do PostgreSQL](https://docs.oracle.com/en-us/iaas/Content/postgresql/policies.htm). Não adicionar um grant amplo a `service psql` com base apenas em uma hipótese de revisão. A leitura dos bundles pelo serviço e a montagem CSI permanecem verificações do bootstrap real. A condição `target.vault.id` é documentada nas [políticas comuns da Oracle](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm) para limitar acesso a uma família de segredos; mantê-la até existir evidência concreta que exija ajuste.

O prazo de 20 minutos é para o vídeo editado, não para provisionamento/validação/teardown. A reconciliação do Argo configurada em 60s também não garante rollout saudável em 60s; salvar a sequência real de commits e operações.

A OCI Cache adiciona automaticamente a `redis-security-list` à subnet de dados. O Terraform preserva essa associação gerenciada pelo serviço com `ignore_changes` somente em `security_list_ids` dessa subnet; os NSGs do projeto continuam versionados.

O chart NGINX2.6.1 é versionado em `platform/charts` com as referências de schema incorporadas localmente. As permissões de secrets são restritas ao namespace do ingress, e a validação de schema permanece ativa. O script `scripts/maintenance/vendor-nginx-chart.py` verifica os hashes das fontes e reproduz o arquivo.
