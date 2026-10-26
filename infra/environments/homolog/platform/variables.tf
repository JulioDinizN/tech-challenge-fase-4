variable "kubeconfig_path" { type = string }
variable "kube_context" { type = string }
variable "region" { type = string }
variable "load_balancer_subnet_id" { type = string }
variable "load_balancer_nsg_id" { type = string }
variable "worker_nsg_id" { type = string }
variable "bootstrap_gitops" {
  description = "Install the GitOps root only after rendered values, images and pull credentials have been reviewed."
  type        = bool
  default     = false
}
variable "gitops_repository" {
  type    = string
  default = "https://github.com/JulioDinizN/tech-challenge-fase-4-gitops.git"
}
