"""Exercise non-secret configuration without contacting Terraform or a cluster."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('configure', ROOT/'scripts/ops/configure-gitops.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SERVICES = ['auth-service','flag-service','targeting-service','evaluation-service','analytics-service']
DB = SERVICES[:3]


def fixture():
    return {
        'deployment_context': {'region':'us-ashburn-1','compartment_id':'ocid1.compartment.oc1..fixture'},
        'postgresql_systems': {s:{'private_ip':f'10.0.32.{10+i}'} for i,s in enumerate(DB)},
        'ocir_repositories': {s:{'image_path':f'iad.ocir.io/fixture/togglemaster/{s}'} for s in SERVICES},
        'vault': {'id':'ocid1.vault.oc1.iad.fixture','secret_names':{
            'postgres_admin_passwords':{s:f'{s}-admin' for s in DB},
            'postgres_app_passwords':{s:f'{s}-app' for s in DB},
            'auth_master_key':'auth-master','internal_api_key':'internal-api'}},
        'redis':{'tls_url':'rediss://cache.fixture:6379'},
        'evaluation_queue':{'id':'ocid1.queue.oc1.iad.fixture','messages_endpoint':'https://queue.fixture'},
        'analytics_table':{'id':'ocid1.nosqltable.oc1.iad.fixture'},
    }


class ConfigureTests(unittest.TestCase):
    def test_initial_values_render_all_workloads_with_immutable_images(self):
        gitops = ROOT.parent/'tech-challenge-fase-4-gitops'
        if not gitops.exists():
            self.skipTest('sibling GitOps checkout required')
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)/'gitops'
            shutil.copytree(gitops,dst,ignore=shutil.ignore_patterns('.git','__pycache__'))
            module.configure(fixture(), dst, 'sha-123456789abc')
            for service in SERVICES:
                result=subprocess.check_output(['kubectl','kustomize',str(dst/'apps'/service/'overlays/homolog')],text=True)
                self.assertIn(f'iad.ocir.io/fixture/togglemaster/{service}:sha-123456789abc',result)
                self.assertNotIn('__OCI_',result)
            self.assertNotIn('__OCI_',subprocess.check_output(['kubectl','kustomize',str(dst/'platform/overlays/homolog')],text=True))

    def test_core_outputs_replace_bootstrap_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'apps').mkdir()
            (root/'platform').mkdir()
            target = root/'platform/resources.yaml'
            target.write_text('region: __OCI_REGION__\nhost: __OCI_AUTH_DB_HOST__\nvault: __OCI_VAULT_ID__\n')
            module.configure(fixture(), root, 'sha-123456789abc')
            self.assertEqual(target.read_text(), 'region: us-ashburn-1\nhost: 10.0.32.10\nvault: ocid1.vault.oc1.iad.fixture\n')

    def test_unpublished_style_tag_and_yaml_injection_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'apps').mkdir(); (root/'platform').mkdir()
            (root/'apps/test.yaml').write_text('value: __OCI_REGION__\n')
            with self.assertRaises(ValueError): module.configure(fixture(),root,'latest')
            values=fixture(); values['deployment_context']['region']='region\ninjected: value'
            with self.assertRaises(ValueError): module.configure(values,root,'sha-123456789abc')
            self.assertEqual((root/'apps/test.yaml').read_text(),'value: __OCI_REGION__\n')


if __name__=='__main__': unittest.main()
