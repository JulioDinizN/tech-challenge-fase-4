resource "helm_release" "csi" {
  name       = "csi-secrets-store"
  namespace  = "kube-system"
  repository = "https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts"
  chart      = "secrets-store-csi-driver"
  version    = "1.6.0"
  atomic     = true
  values     = [yamlencode({ syncSecret = { enabled = true }, enableSecretRotation = true, rotationPollInterval = "2m" })]
}
resource "helm_release" "oci_secrets" {
  name       = "oci-provider"
  namespace  = "kube-system"
  repository = "https://oracle.github.io/oci-secrets-store-csi-driver-provider/charts"
  chart      = "oci-secrets-store-csi-driver-provider"
  version    = "0.4.1"
  atomic     = true
  depends_on = [helm_release.csi]
  values = [yamlencode({
    secrets-store-csi-driver = { install = false }
    provider = { oci = { auth = { types = {
      instance = { enabled = false }
      user     = { enabled = false }
      workload = { enabled = true, resourcePrincipalVersion = "2.2", resourcePrincipalRegion = var.region }
    } } } }
  })]
}
resource "helm_release" "metrics" {
  name       = "metrics-server"
  namespace  = "kube-system"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  version    = "3.13.0"
  atomic     = true
}
resource "helm_release" "ingress" {
  name             = "nginx-ingress"
  namespace        = "nginx-ingress"
  create_namespace = true
  # Upstream chart with its external schema references bundled locally.
  chart   = "${path.module}/charts/nginx-ingress-2.6.1.tgz"
  version = "2.6.1"
  atomic  = true
  timeout = 600
  values = [yamlencode({ controller = {
    watchNamespace        = "togglemaster"
    watchSecretNamespace  = "nginx-ingress"
    nginxplus             = false
    image                 = { repository = "docker.io/nginx/nginx-ingress" }
    enableCustomResources = false
    allowEmptyIngressHost = true
    replicaCount          = 1
    service = { annotations = {
      "oci.oraclecloud.com/load-balancer-type"                      = "lb"
      "service.beta.kubernetes.io/oci-load-balancer-subnet1"        = var.load_balancer_subnet_id
      "oci.oraclecloud.com/oci-network-security-groups"             = var.load_balancer_nsg_id
      "oci.oraclecloud.com/security-rule-management-mode"           = "None"
      "oci.oraclecloud.com/oci-backend-network-security-group"      = var.worker_nsg_id
      "service.beta.kubernetes.io/oci-load-balancer-shape"          = "flexible"
      "service.beta.kubernetes.io/oci-load-balancer-shape-flex-min" = "10"
      "service.beta.kubernetes.io/oci-load-balancer-shape-flex-max" = "10"
    } }
  } })]
}
resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "10.9.0"
  atomic           = true
  timeout          = 600
  values = [yamlencode({
    server = { service = { type = "ClusterIP" } }
    configs = { cm = {
      "timeout.reconciliation" = "60s"
      # The NGINX controller does not publish the load balancer address on the Ingress status,
      # so Argo CD's default health check would keep the Ingress (and every later sync wave,
      # including the database init Jobs) in Progressing forever.
      "resource.customizations.health.networking.k8s.io_Ingress" = "hs = {}\nhs.status = \"Healthy\"\nreturn hs\n"
    } }
  })]
}
resource "helm_release" "gitops_root" {
  count      = var.bootstrap_gitops ? 1 : 0
  name       = "togglemaster-gitops-root"
  namespace  = "argocd"
  chart      = "${path.module}/charts/gitops-root"
  depends_on = [helm_release.argocd, helm_release.oci_secrets, helm_release.ingress, helm_release.metrics]
  values     = [yamlencode({ repository = var.gitops_repository })]
}
