output "oke_cluster" {
  description = "OKE cluster identifiers and API endpoints."
  value = {
    id              = oci_containerengine_cluster.main.id
    name            = oci_containerengine_cluster.main.name
    kubernetes      = oci_containerengine_cluster.main.endpoints[0].kubernetes
    public_endpoint = oci_containerengine_cluster.main.endpoints[0].public_endpoint
    node_pool_id    = oci_containerengine_node_pool.main.id
  }
}

output "deployment_context" {
  description = "Non-secret OCI values consumed by the Kubernetes rendering and add-on scripts."
  value = {
    region                  = var.region
    compartment_id          = var.compartment_id
    kubernetes_namespace    = var.kubernetes_namespace
    postgres_admin_username = var.postgres_admin_username
    oci_config_profile      = var.oci_config_profile
  }
}

output "kubeconfig_command" {
  description = "Command to run manually after provisioning to create a local kubeconfig."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.main.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0 --profile ${var.oci_config_profile}"
}

output "ocir_repositories" {
  description = "Private OCIR repository IDs and image prefixes."
  value = {
    for name, repository in oci_artifacts_container_repository.services : name => {
      id         = repository.id
      image_path = "${var.ocir_region_key}.ocir.io/${var.ocir_namespace}/${repository.display_name}"
    }
  }
}

output "postgresql_systems" {
  description = "Private PostgreSQL endpoints and database names. Password values remain in OCI Vault."
  value = {
    for service, database in oci_psql_db_system.services : service => {
      id            = database.id
      database_name = local.database_names[service]
      private_ip    = database.network_details[0].primary_db_endpoint_private_ip
      port          = 5432
      username      = var.postgres_admin_username
    }
  }
}

output "vault" {
  description = "OCI Vault metadata and generated secret names used by the Kubernetes CSI overlay. No secret values are exported."
  value = {
    id     = oci_kms_vault.application.id
    key_id = oci_kms_key.application.id
    secret_names = {
      postgres_admin_passwords = {
        for service, secret in oci_vault_secret.postgres_admin_password : service => secret.secret_name
      }
      postgres_app_passwords = {
        for service, secret in oci_vault_secret.postgres_app_password : service => secret.secret_name
      }
      auth_master_key        = oci_vault_secret.auth_master_key.secret_name
      internal_api_key       = oci_vault_secret.internal_api_key.secret_name
      self_healing_token     = oci_vault_secret.self_healing_token.secret_name
      grafana_admin_user     = oci_vault_secret.grafana_admin_user.secret_name
      grafana_admin_password = oci_vault_secret.grafana_admin_password.secret_name
      observability_integrations = {
        for name, secret in oci_vault_secret.observability_integration : name => secret.secret_name
      }
    }
  }
}

output "redis" {
  description = "Private TLS endpoint for the evaluation cache."
  value = {
    id           = oci_redis_redis_cluster.evaluation.id
    primary_fqdn = oci_redis_redis_cluster.evaluation.primary_fqdn
    tls_url      = "rediss://${oci_redis_redis_cluster.evaluation.primary_fqdn}:6379"
  }
}

output "evaluation_queue" {
  description = "OCI Queue identifiers required by the future OCI SDK integration."
  value = {
    id                = oci_queue_queue.evaluations.id
    messages_endpoint = oci_queue_queue.evaluations.messages_endpoint
  }
}

output "analytics_table" {
  description = "OCI NoSQL table identifiers required by the future OCI SDK integration."
  value = {
    id   = oci_nosql_table.analytics.id
    name = oci_nosql_table.analytics.name
  }
}

output "network" {
  description = "Network IDs needed by later Kubernetes and ingress configuration."
  value = {
    vcn_id                  = oci_core_vcn.main.id
    api_subnet_id           = oci_core_subnet.api.id
    load_balancer_subnet_id = oci_core_subnet.load_balancer.id
    worker_subnet_id        = oci_core_subnet.workers.id
    data_subnet_id          = oci_core_subnet.data.id
    load_balancer_nsg_id    = oci_core_network_security_group.load_balancer.id
    worker_nsg_id           = oci_core_network_security_group.workers.id
    data_nsg_id             = oci_core_network_security_group.data.id
  }
}

output "workload_identity_policy_id" {
  description = "IAM policy OCID when workload identity is enabled."
  value       = try(oci_identity_policy.oke_workloads[0].id, null)
}
