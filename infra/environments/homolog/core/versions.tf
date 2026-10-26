terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  backend "oci" {
    bucket    = "configured-at-init"
    namespace = "configured-at-init"
    key       = "togglemaster/phase4/homolog/core.tfstate"
  }
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "8.21.0"
    }
  }
}
