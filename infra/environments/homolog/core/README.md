# Core — infraestrutura OCI

Root que instancia `../../../modules/oci-runtime`: rede, OKE, registros OCIR, bancos, cache, fila, NoSQL, Vault e IAM.

Os parâmetros de ambiente usam `terraform.tfvars.example` e `backend.hcl.example` como modelos. Os arquivos reais são locais e ignorados pelo Git. O backend remoto usa a chave própria de core, separada de backend e platform.

Para um checkout já inicializado, executar `terraform -chdir=infra/environments/homolog/core plan -input=false`. Não inicializar sem backend sobre um diretório de operação já configurado. Antes de uma nova implantação, conferir disponibilidade da imagem OKE, versão Kubernetes, quotas, shapes e proprietário de cada recurso.

Procedimento completo em [operações](../../../../docs/operations.md).
