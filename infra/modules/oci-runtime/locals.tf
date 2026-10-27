locals {
  service_names = toset([
    "auth-service",
    "flag-service",
    "targeting-service",
    "evaluation-service",
    "analytics-service",
    "self-healing",
  ])

  observability_integrations = {
    new-relic-license-key     = "New Relic ingest license key used by the OTel Collector trace exporter."
    pagerduty-integration-key = "PagerDuty Events API v2 integration key used by Grafana Alerting."
    discord-webhook-url       = "Discord webhook URL used by Grafana Alerting notifications."
  }

  database_names = {
    auth-service      = "auth_db"
    flag-service      = "flags_db"
    targeting-service = "targeting_db"
  }

  selected_availability_domain = coalesce(
    var.availability_domain_name,
    data.oci_identity_availability_domains.available.availability_domains[0].name,
  )

  common_tags = merge({
    Project   = var.project_name
    ManagedBy = "Terraform"
    Course    = "POSTECH-Tech-Challenge-Fase-4"
  }, var.freeform_tags)
}

check "subnets_belong_to_vcn" {
  assert {
    condition = alltrue([
      for cidr in [
        var.network_cidrs.api,
        var.network_cidrs.load_balancer,
        var.network_cidrs.workers,
        var.network_cidrs.data,
        ] : (
        tonumber(split("/", cidr)[1]) >= tonumber(split("/", var.network_cidrs.vcn)[1]) &&
        cidrhost(var.network_cidrs.vcn, 0) == cidrhost(
          "${cidrhost(cidr, 0)}/${split("/", var.network_cidrs.vcn)[1]}",
          0,
        )
      )
    ])
    error_message = "All subnet CIDRs must be contained by network_cidrs.vcn."
  }
}

check "selected_availability_domain_exists" {
  assert {
    condition = contains(
      data.oci_identity_availability_domains.available.availability_domains[*].name,
      local.selected_availability_domain,
    )
    error_message = "availability_domain_name is not available in this tenancy and region."
  }
}

check "workload_identity_requires_enhanced_oke" {
  assert {
    condition     = !var.create_workload_identity_policy || var.oke_cluster_type == "ENHANCED_CLUSTER"
    error_message = "OKE workload identity requires oke_cluster_type = ENHANCED_CLUSTER. Disable create_workload_identity_policy when using a basic cluster."
  }
}
