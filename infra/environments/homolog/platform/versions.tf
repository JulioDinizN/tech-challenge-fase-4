terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  backend "oci" {
    bucket    = "configured-at-init"
    namespace = "configured-at-init"
    key       = "togglemaster/phase4/homolog/platform.tfstate"
  }
  required_providers {
    helm = { source = "hashicorp/helm", version = "3.2.0" }
  }
}
provider "helm" {
  kubernetes = {
    config_path    = var.kubeconfig_path
    config_context = var.kube_context
  }
}
