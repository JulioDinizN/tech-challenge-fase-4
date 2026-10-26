# ToggleMaster Phase 4 Workspace Guide

## Scope

- This repository owns service sources, local Docker, Terraform, CI, scripts, and delivery documentation.
- Kubernetes desired state belongs in JulioDinizN/tech-challenge-fase-4-gitops.
- Preserve service contracts and the separation between Terraform infrastructure and GitOps workloads.
- Phase 4 adds observability on top of Phase 3: OpenTelemetry instrumentation, OTel Collector, Prometheus, Loki, Grafana, APM, alerting, incident management, ChatOps and Self-Healing.
- Monitoring stack Helm charts belong in the GitOps repository, not in the Terraform platform root.

## Hard boundaries

- Never run terraform apply/destroy, mutating OCI CLI commands, Helm installs, kubectl apply, Argo syncs, or image pushes without explicit authorization.
- Never commit OCI keys or tokens, database passwords, Vault secret contents, kubeconfigs, Terraform state, or saved plans.
- Service CI must not receive application runtime secrets.
- CI may publish only from main after all gates and only when ENABLE_OCIR_PUBLISH=true.
- CI must never deploy directly; promotion ends in a GitOps commit.
- Self-Healing is the only automation allowed to act on the cluster, limited to restarting Deployments in the togglemaster namespace.
- Never add Co-Authored-By lines to commit messages.

## Monorepo rules

- Keep .ci/services.json synchronized with services/.
- Shared CI logic belongs in .github/workflows/_service-ci.yml.
- Test and publish only changed services unless a shared file changes.
- Consolidate promotions into one GitOps commit.
- Use immutable sha-<12 hex> tags; never deploy latest.

## Terraform ownership

- The only roots are infra/environments/homolog/backend, core and platform.
- backend owns the state bucket and keeps the Phase 3 state key because that state still owns the retained bucket; core owns OCI resources through modules/oci-runtime.
- platform owns cluster add-ons and Argo bootstrap through Helm.
- Use native OCI backends with distinct Object Storage keys.
- Application manifests belong only in the GitOps repository.
- Never change state ownership as part of documentation or repository cleanup.

## Secrets

- APM, incident management and ChatOps credentials follow the same rule as runtime secrets: Vault identifiers only, never values.

- OCI Vault remains the runtime source of truth.
- OKE workloads use dedicated ServiceAccounts and Workload Identity.
- OCIR image pull credentials are a separate bootstrap concern.
- GitOps may contain secret identifiers, never secret values.
