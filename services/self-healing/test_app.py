import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import app as self_healing

TEST_TOKEN = "test-token"  # nosec B105 - valor fictício usado apenas nos testes
MISSING_FILE = "/nonexistent"


def notification(status="firing", deployment="auth-service"):
    return {
        "status": status,
        "alerts": [
            {
                "status": status,
                "labels": {"alertname": "AuthService5xx", "deployment": deployment},
            }
        ],
    }


class FakeKubernetesAPI(BaseHTTPRequestHandler):
    requests: ClassVar[list] = []

    def do_PATCH(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeKubernetesAPI.requests.append(
            {"path": self.path, "content_type": self.headers["Content-Type"], "body": body}
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class HealerTests(unittest.TestCase):
    def setUp(self):
        FakeKubernetesAPI.requests = []
        self.api = serve(FakeKubernetesAPI)
        self.config = self_healing.Config(
            {
                "SELF_HEALING_TOKEN": TEST_TOKEN,
                "ALLOWED_DEPLOYMENTS": "auth-service,flag-service",
                "KUBERNETES_API_URL": f"http://127.0.0.1:{self.api.server_port}",
                "COOLDOWN_SECONDS": "300",
            }
        )
        self.now = 1000.0
        kubernetes = self_healing.KubernetesClient(
            self.config.api_url, token_path=MISSING_FILE, ca_path=MISSING_FILE  # nosec B106
        )
        self.healer = self_healing.Healer(self.config, kubernetes, clock=lambda: self.now)

    def tearDown(self):
        self.api.shutdown()
        self.api.server_close()

    def test_firing_alert_patches_restart_annotation(self):
        results = self.healer.handle_notification(notification())

        self.assertEqual(results, [{"deployment": "auth-service", "action": "restarted"}])
        (request,) = FakeKubernetesAPI.requests
        self.assertEqual(
            request["path"], "/apis/apps/v1/namespaces/togglemaster/deployments/auth-service"
        )
        self.assertEqual(request["content_type"], "application/strategic-merge-patch+json")
        annotations = request["body"]["spec"]["template"]["metadata"]["annotations"]
        self.assertIn(self_healing.RESTART_ANNOTATION, annotations)

    def test_resolved_alert_is_ignored(self):
        results = self.healer.handle_notification(notification(status="resolved"))

        self.assertEqual(results[0]["action"], "skipped")
        self.assertEqual(FakeKubernetesAPI.requests, [])

    def test_deployment_outside_allowlist_is_ignored(self):
        results = self.healer.handle_notification(notification(deployment="argocd-server"))

        self.assertEqual(results[0]["action"], "skipped")
        self.assertEqual(FakeKubernetesAPI.requests, [])

    def test_cooldown_prevents_restart_loop(self):
        self.healer.handle_notification(notification())
        self.now += 60
        second = self.healer.handle_notification(notification())
        self.now += 300
        third = self.healer.handle_notification(notification())

        self.assertEqual(second[0]["action"], "skipped")
        self.assertEqual(third[0]["action"], "restarted")
        self.assertEqual(len(FakeKubernetesAPI.requests), 2)

    def test_dry_run_does_not_call_api(self):
        self.config.dry_run = True

        results = self.healer.handle_notification(notification())

        self.assertEqual(results[0]["action"], "dry-run")
        self.assertEqual(FakeKubernetesAPI.requests, [])

    def test_failed_restart_releases_cooldown(self):
        self.config.api_url = "http://127.0.0.1:9"
        self.healer.kubernetes.api_url = self.config.api_url

        failed = self.healer.handle_notification(notification())

        self.assertEqual(failed[0]["action"], "failed")
        self.assertNotIn("auth-service", self.healer.last_restart)


class WebhookTests(unittest.TestCase):
    def setUp(self):
        config = self_healing.Config(
            {"SELF_HEALING_TOKEN": TEST_TOKEN, "ALLOWED_DEPLOYMENTS": "auth-service", "DRY_RUN": "true"}
        )
        healer = self_healing.Healer(config, kubernetes=None)
        self.server = serve(self_healing.make_handler(config, healer))
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, token):
        request = urllib.request.Request(
            self.url + "/webhook",
            data=json.dumps(notification()).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=5)  # nosec B310

    def test_rejects_invalid_token(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.post("wrong")
        self.assertEqual(context.exception.code, 401)

    def test_accepts_valid_token(self):
        with self.post(TEST_TOKEN) as response:
            body = json.loads(response.read())
        self.assertEqual(body["results"][0]["action"], "dry-run")

    def test_health(self):
        with urllib.request.urlopen(self.url + "/health", timeout=5) as response:  # nosec B310
            self.assertEqual(response.status, 200)


class ConfigTests(unittest.TestCase):
    def test_requires_token_and_allowlist(self):
        errors = self_healing.Config({}).validate()
        self.assertEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
