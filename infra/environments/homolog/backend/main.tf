terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  backend "oci" {
    bucket    = "configured-at-init"
    namespace = "configured-at-init"
    key       = "togglemaster/phase4/homolog/backend.tfstate"
  }
  required_providers {
    oci = { source = "oracle/oci", version = "8.21.0" }
  }
}
provider "oci" {
  region              = var.region
  config_file_profile = var.oci_config_profile
}
variable "region" { type = string }
variable "compartment_id" { type = string }
variable "namespace" { type = string }
variable "bucket_name" { type = string }
variable "oci_config_profile" { default = "DEFAULT" }
resource "oci_objectstorage_bucket" "state" {
  compartment_id = var.compartment_id
  namespace      = var.namespace
  name           = var.bucket_name
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  storage_tier   = "Standard"
  lifecycle { prevent_destroy = true }
}
output "backend" {
  value = { bucket = oci_objectstorage_bucket.state.name, namespace = var.namespace, region = var.region }
}
