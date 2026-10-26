# OCI runtime module

Network, OKE, PostgreSQL, Cache, Queue, NoSQL, OCIR, Vault and workload policies for Phase 4. Resources are separated by responsibility into Terraform files and composed by `infra/environments/homolog/core`. Provider configuration stays in the root.

Core is the single Terraform state owner of these resources. Reusing an existing environment requires reviewing ownership and importing resources where appropriate before applying. Repository cleanup does not migrate or destroy state.
