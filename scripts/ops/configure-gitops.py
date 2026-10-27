#!/usr/bin/env python3
"""Fill non-secret GitOps placeholders from core outputs. Never applies or pushes."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def required(mapping, key):
    value = mapping[key]
    if value is None or value == "":
        raise ValueError(f"Terraform output {key} is empty")
    return str(value)


def replacements(outputs, image_tag):
    context = outputs["deployment_context"]
    databases = outputs["postgresql_systems"]
    repositories = outputs["ocir_repositories"]
    vault = outputs["vault"]
    names = vault["secret_names"]
    integrations = names.get("observability_integrations", {})

    values = {
        "__IMAGE_TAG__": image_tag,
        "__OCI_REGION__": required(context, "region"),
        "__OCI_COMPARTMENT_OCID__": required(context, "compartment_id"),
        "__OCI_AUTH_DB_HOST__": required(databases["auth-service"], "private_ip"),
        "__OCI_FLAG_DB_HOST__": required(databases["flag-service"], "private_ip"),
        "__OCI_TARGETING_DB_HOST__": required(
            databases["targeting-service"], "private_ip"
        ),
        "__OCI_REDIS_URL__": required(outputs["redis"], "tls_url"),
        "__OCI_QUEUE_OCID__": required(outputs["evaluation_queue"], "id"),
        "__OCI_QUEUE_MESSAGES_ENDPOINT__": required(
            outputs["evaluation_queue"], "messages_endpoint"
        ),
        "__OCI_NOSQL_TABLE_OCID__": required(outputs["analytics_table"], "id"),
        "__OCI_VAULT_ID__": required(vault, "id"),
        "__OCI_AUTH_ADMIN_PASSWORD_SECRET_NAME__": required(
            names["postgres_admin_passwords"], "auth-service"
        ),
        "__OCI_FLAG_ADMIN_PASSWORD_SECRET_NAME__": required(
            names["postgres_admin_passwords"], "flag-service"
        ),
        "__OCI_TARGETING_ADMIN_PASSWORD_SECRET_NAME__": required(
            names["postgres_admin_passwords"], "targeting-service"
        ),
        "__OCI_AUTH_APP_PASSWORD_SECRET_NAME__": required(
            names["postgres_app_passwords"], "auth-service"
        ),
        "__OCI_FLAG_APP_PASSWORD_SECRET_NAME__": required(
            names["postgres_app_passwords"], "flag-service"
        ),
        "__OCI_TARGETING_APP_PASSWORD_SECRET_NAME__": required(
            names["postgres_app_passwords"], "targeting-service"
        ),
        "__OCI_AUTH_MASTER_KEY_SECRET_NAME__": required(names, "auth_master_key"),
        "__OCI_INTERNAL_API_KEY_SECRET_NAME__": required(names, "internal_api_key"),
        "__OCI_SELF_HEALING_TOKEN_SECRET_NAME__": required(names, "self_healing_token"),
        "__OCI_GRAFANA_ADMIN_USER_SECRET_NAME__": required(names, "grafana_admin_user"),
        "__OCI_GRAFANA_ADMIN_PASSWORD_SECRET_NAME__": required(names, "grafana_admin_password"),
        "__OCI_NEW_RELIC_LICENSE_KEY_SECRET_NAME__": required(integrations, "new-relic-license-key"),
        "__OCI_PAGERDUTY_INTEGRATION_KEY_SECRET_NAME__": required(integrations, "pagerduty-integration-key"),
        "__OCI_DISCORD_WEBHOOK_URL_SECRET_NAME__": required(integrations, "discord-webhook-url"),
    }

    for service in (
        "auth-service",
        "flag-service",
        "targeting-service",
        "evaluation-service",
        "analytics-service",
        "self-healing",
    ):
        token = f"__OCIR_{service.upper().replace('-', '_')}_IMAGE__"
        values[token] = required(repositories[service], "image_path")

    return values


def configure(outputs, gitops, tag):
    if not re.fullmatch(r'sha-[0-9a-f]{12}', tag):
        raise ValueError('initial image tag must be sha-<12 hex> and already published for all catalog images')
    values = replacements(outputs, tag)
    pending = {}
    for p in [f for d in ('apps', 'platform', 'observability') for f in (gitops/d).rglob('*.yaml')]:
        text = p.read_text()
        for token, value in values.items():
            # Values are inserted into plain YAML scalars; reject YAML injection.
            if not re.fullmatch(r'[A-Za-z0-9_./:@-]+', value):
                raise ValueError(f'invalid non-secret output for {token}')
            text = text.replace(token, value)
        if p.name == 'kustomization.yaml' and 'overlays' in p.parts and 'apps' in p.parts:
            service = p.parts[p.parts.index('apps')+1]
            image = outputs['ocir_repositories'][service]['image_path']
            text = re.sub(r'newName: .*', 'newName: ' + image, text)
            text = re.sub(r'newTag: .*', 'newTag: ' + tag, text)
        if re.search(r'__[A-Z0-9_]+__|ocir\.invalid|replace-with', text):
            raise ValueError(f'unresolved placeholders in {p.relative_to(gitops)}')
        pending[p] = text
    # Validate all substitutions before writing any file; repeated use preserves non-image settings.
    for p, text in pending.items():
        p.write_text(text)
    print('Configured non-secret GitOps inputs. Review diff and run validator --ready. Nothing applied or pushed.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gitops-root', required=True, type=Path)
    parser.add_argument('--initial-image-tag', required=True)
    parser.add_argument('--outputs-json', type=Path, help='Offline fixture or terraform output -json file; never a state file')
    args = parser.parse_args()
    raw = args.outputs_json.read_text() if args.outputs_json else subprocess.check_output(['terraform', f'-chdir={ROOT}/infra/environments/homolog/core', 'output', '-json'], text=True)
    document = json.loads(raw)
    outputs = {k: v['value'] for k, v in document.items()}
    configure(outputs, args.gitops_root.resolve(), args.initial_image_tag)


if __name__ == '__main__':
    main()
