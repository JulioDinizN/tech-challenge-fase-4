variable "project_name" {
  description = "Lowercase name prefix used for OCI resources."
  type        = string
  default     = "togglemaster"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,29}$", var.project_name))
    error_message = "project_name must start with a letter and contain only lowercase letters, numbers, and hyphens."
  }
}

variable "region" {
  description = "OCI region identifier, for example sa-saopaulo-1."
  type        = string
}

variable "tenancy_ocid" {
  description = "OCI tenancy OCID used to discover availability domains."
  type        = string
}

variable "compartment_id" {
  description = "OCID of the compartment that will contain the project resources."
  type        = string
}

variable "oci_config_profile" {
  description = "Profile from ~/.oci/config used by the OCI provider."
  type        = string
  default     = "DEFAULT"
}

variable "oci_auth" {
  description = "OCI provider authentication method."
  type        = string
  default     = "ApiKey"

  validation {
    condition = contains([
      "ApiKey",
      "SecurityToken",
      "InstancePrincipal",
      "ResourcePrincipal",
    ], var.oci_auth)
    error_message = "oci_auth must be ApiKey, SecurityToken, InstancePrincipal, or ResourcePrincipal."
  }
}

variable "ocir_namespace" {
  description = "Object Storage namespace used in OCIR image paths."
  type        = string
}

variable "ocir_region_key" {
  description = "Short OCIR region key, for example gru for Sao Paulo."
  type        = string
}

variable "api_allowed_cidrs" {
  description = "CIDR blocks allowed to reach the public OKE Kubernetes API endpoint. Prefer a /32 for the operator IP."
  type        = set(string)

  validation {
    condition = length(var.api_allowed_cidrs) > 0 && alltrue([
      for cidr in var.api_allowed_cidrs : can(cidrhost(cidr, 0))
    ])
    error_message = "api_allowed_cidrs must contain at least one valid CIDR block."
  }
}

variable "network_cidrs" {
  description = "CIDR plan for the VCN and its regional subnets."
  type = object({
    vcn           = string
    api           = string
    load_balancer = string
    workers       = string
    data          = string
  })
  default = {
    vcn           = "10.0.0.0/16"
    api           = "10.0.0.0/28"
    load_balancer = "10.0.1.0/24"
    workers       = "10.0.16.0/20"
    data          = "10.0.32.0/24"
  }

  validation {
    condition = alltrue([
      for cidr in values(var.network_cidrs) : can(cidrhost(cidr, 0))
    ])
    error_message = "Every network_cidrs value must be a valid CIDR block."
  }
}

variable "kubernetes_version" {
  description = "OKE Kubernetes version supported in the selected region, including the v prefix."
  type        = string
}

variable "oke_cluster_type" {
  description = "OKE control-plane type. Enhanced is required for workload identity."
  type        = string
  default     = "ENHANCED_CLUSTER"

  validation {
    condition     = contains(["BASIC_CLUSTER", "ENHANCED_CLUSTER"], var.oke_cluster_type)
    error_message = "oke_cluster_type must be BASIC_CLUSTER or ENHANCED_CLUSTER."
  }
}

variable "node_image_id" {
  description = "OCID of an OKE image compatible with kubernetes_version and node_shape."
  type        = string
}

variable "node_shape" {
  description = "Compute shape for OKE managed worker nodes."
  type        = string
  default     = "VM.Standard.E3.Flex"
}

variable "node_pool_size" {
  description = "Desired number of OKE worker nodes."
  type        = number
  default     = 2

  validation {
    condition     = var.node_pool_size >= 1
    error_message = "node_pool_size must be at least 1."
  }
}

variable "node_pool_name" {
  description = "Optional explicit OKE node-pool name, useful for controlled pool replacement."
  type        = string
  default     = null

  validation {
    condition     = var.node_pool_name == null || length(trimspace(var.node_pool_name)) > 0
    error_message = "node_pool_name must be null or a non-empty string."
  }
}

variable "node_availability_domain_count" {
  description = "Optional number of availability domains offered to OKE for worker placement."
  type        = number
  default     = null

  validation {
    condition     = var.node_availability_domain_count == null || var.node_availability_domain_count >= 1
    error_message = "node_availability_domain_count must be null or at least 1."
  }
}

variable "node_availability_domain_start_index" {
  description = "Zero-based availability-domain index at which worker placement starts."
  type        = number
  default     = 0

  validation {
    condition     = var.node_availability_domain_start_index >= 0
    error_message = "node_availability_domain_start_index must be zero or greater."
  }
}

variable "node_ocpus" {
  description = "OCPUs allocated to each flexible OKE worker node."
  type        = number
  default     = 1

  validation {
    condition     = var.node_ocpus > 0
    error_message = "node_ocpus must be greater than zero."
  }
}

variable "node_memory_in_gbs" {
  description = "Memory allocated to each flexible OKE worker node."
  type        = number
  default     = 8

  validation {
    condition     = var.node_memory_in_gbs >= 1
    error_message = "node_memory_in_gbs must be at least 1."
  }
}

variable "node_boot_volume_size_in_gbs" {
  description = "Boot volume size for each OKE worker node."
  type        = number
  default     = 50

  validation {
    condition     = var.node_boot_volume_size_in_gbs >= 50
    error_message = "OKE worker boot volumes must be at least 50 GB."
  }
}

variable "ssh_public_key" {
  description = "Optional SSH public key installed on OKE worker nodes."
  type        = string
  default     = null
  nullable    = true
}

variable "availability_domain_name" {
  description = "Optional availability-domain name for AD-local PostgreSQL storage. Defaults to the first AD."
  type        = string
  default     = null
  nullable    = true
}

variable "postgres_admin_username" {
  description = "Administrator username shared by the three independent PostgreSQL systems."
  type        = string
  default     = "togglemaster_admin"
}

variable "postgres_db_version" {
  description = "PostgreSQL major version supported by OCI Database with PostgreSQL."
  type        = string
  default     = "14"
}

variable "postgres_shapes" {
  description = "OCI Database with PostgreSQL flexible shape selected independently for each service."
  type        = map(string)
  default = {
    auth-service      = "PostgreSQL.VM.Standard.E5.Flex"
    flag-service      = "PostgreSQL.VM.Standard.E5.Flex"
    targeting-service = "PostgreSQL.VM.Standard3.Flex"
  }

  validation {
    condition = (
      length(var.postgres_shapes) == 3 &&
      alltrue([
        for service in ["auth-service", "flag-service", "targeting-service"] :
        contains(keys(var.postgres_shapes), service)
      ]) &&
      alltrue([
        for shape in values(var.postgres_shapes) : startswith(shape, "PostgreSQL.VM.")
      ])
    )
    error_message = "postgres_shapes must define a PostgreSQL.VM shape for auth-service, flag-service, and targeting-service."
  }
}

variable "postgres_instance_count" {
  description = "Number of instances in each PostgreSQL DB system."
  type        = number
  default     = 1

  validation {
    condition     = var.postgres_instance_count >= 1
    error_message = "postgres_instance_count must be at least 1."
  }
}

variable "postgres_ocpus" {
  description = "OCPUs allocated independently to each PostgreSQL service instance."
  type        = map(number)
  default = {
    auth-service      = 1
    flag-service      = 1
    targeting-service = 2
  }

  validation {
    condition = (
      length(var.postgres_ocpus) == 3 &&
      alltrue([
        for service in ["auth-service", "flag-service", "targeting-service"] :
        contains(keys(var.postgres_ocpus), service)
      ]) &&
      alltrue([for ocpus in values(var.postgres_ocpus) : ocpus >= 1])
    )
    error_message = "postgres_ocpus must define at least 1 OCPU for auth-service, flag-service, and targeting-service."
  }
}

variable "postgres_memory_in_gbs" {
  description = "Memory allocated independently to each PostgreSQL service instance."
  type        = map(number)
  default = {
    auth-service      = 16
    flag-service      = 16
    targeting-service = 32
  }

  validation {
    condition = (
      length(var.postgres_memory_in_gbs) == 3 &&
      alltrue([
        for service in ["auth-service", "flag-service", "targeting-service"] :
        contains(keys(var.postgres_memory_in_gbs), service)
      ]) &&
      alltrue([for memory in values(var.postgres_memory_in_gbs) : memory >= 16])
    )
    error_message = "postgres_memory_in_gbs must define at least 16 GB for auth-service, flag-service, and targeting-service."
  }
}

variable "postgres_regionally_durable" {
  description = "Use regionally durable PostgreSQL storage instead of AD-local storage."
  type        = bool
  default     = false
}

variable "redis_node_count" {
  description = "Number of nodes in the non-sharded OCI Cache cluster."
  type        = number
  default     = 1

  validation {
    condition     = var.redis_node_count >= 1 && var.redis_node_count <= 5
    error_message = "redis_node_count must be between 1 and 5."
  }
}

variable "redis_node_memory_in_gbs" {
  description = "Memory allocated to each OCI Cache node."
  type        = number
  default     = 2

  validation {
    condition     = var.redis_node_memory_in_gbs >= 2 && var.redis_node_memory_in_gbs <= 500
    error_message = "redis_node_memory_in_gbs must be between 2 and 500."
  }
}

variable "redis_software_version" {
  description = "OCI Cache engine version."
  type        = string
  default     = "REDIS_7_0"

  validation {
    condition     = contains(["REDIS_7_0", "VALKEY_7_2", "VALKEY_8_1"], var.redis_software_version)
    error_message = "redis_software_version must be REDIS_7_0, VALKEY_7_2, or VALKEY_8_1."
  }
}

variable "queue_retention_in_seconds" {
  description = "OCI Queue message retention period."
  type        = number
  default     = 604800
}

variable "queue_visibility_in_seconds" {
  description = "OCI Queue visibility timeout used by analytics consumers."
  type        = number
  default     = 30
}

variable "nosql_table_name" {
  description = "OCI NoSQL analytics table name."
  type        = string
  default     = "ToggleMasterAnalytics"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_]{0,255}$", var.nosql_table_name))
    error_message = "nosql_table_name must start with a letter and contain only letters, numbers, and underscores."
  }
}

variable "nosql_read_units" {
  description = "Provisioned read units for the analytics table."
  type        = number
  default     = 10
}

variable "nosql_write_units" {
  description = "Provisioned write units for the analytics table."
  type        = number
  default     = 10
}

variable "nosql_storage_in_gbs" {
  description = "Maximum storage for the analytics table."
  type        = number
  default     = 5
}

variable "kubernetes_namespace" {
  description = "Future Kubernetes namespace used in OKE workload-identity policies."
  type        = string
  default     = "togglemaster"
}

variable "create_workload_identity_policy" {
  description = "Create least-privilege policies for Queue, NoSQL, and the OCI Vault CSI provider workloads."
  type        = bool
  default     = true
}

variable "freeform_tags" {
  description = "Additional free-form tags merged into all supported resources."
  type        = map(string)
  default     = {}
}

variable "observability_namespace" {
  description = "Kubernetes namespace of the monitoring stack, used in OKE workload-identity policies."
  type        = string
  default     = "observability"
}
