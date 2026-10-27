"""Self-Healing: recebe o webhook do Grafana Alerting e reinicia o Deployment afetado.

O reinício usa o mesmo patch de `kubectl rollout restart`: altera a anotação
`kubectl.kubernetes.io/restartedAt` do template do pod. Somente a biblioteca
padrão é usada, para manter a imagem pequena e sem dependências.
"""

import hmac
import json
import logging
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE_ACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
RESTART_ANNOTATION = "kubectl.kubernetes.io/restartedAt"
MAX_BODY_BYTES = 1024 * 1024


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry, ensure_ascii=False)


log = logging.getLogger("self-healing")


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def event(level, message, **fields):
    log.log(level, message, extra={"fields": fields})


class Config:
    def __init__(self, env=os.environ):
        self.token = env.get("SELF_HEALING_TOKEN", "")
        self.namespace = env.get("TARGET_NAMESPACE", "togglemaster")
        self.allowed = {
            name.strip()
            for name in env.get("ALLOWED_DEPLOYMENTS", "").split(",")
            if name.strip()
        }
        self.cooldown_seconds = int(env.get("COOLDOWN_SECONDS", "300"))
        self.dry_run = env.get("DRY_RUN", "false").lower() == "true"
        self.api_url = env.get("KUBERNETES_API_URL", "https://kubernetes.default.svc").rstrip("/")
        self.port = int(env.get("PORT", "8080"))

    def validate(self):
        errors = []
        if not self.token:
            errors.append("SELF_HEALING_TOKEN deve ser definida")
        if not self.allowed:
            errors.append("ALLOWED_DEPLOYMENTS deve listar ao menos um Deployment")
        if not self.api_url.startswith(("https://", "http://")):
            errors.append("KUBERNETES_API_URL deve usar http(s)")
        return errors


class KubernetesClient:
    """Cliente mínimo da API do Kubernetes usando a conta de serviço do pod."""

    def __init__(self, api_url, token_path=None, ca_path=None):
        self.api_url = api_url
        self.token_path = token_path or os.path.join(SERVICE_ACCOUNT_DIR, "token")
        ca_path = ca_path or os.path.join(SERVICE_ACCOUNT_DIR, "ca.crt")
        self.context = ssl.create_default_context(cafile=ca_path) if os.path.exists(ca_path) else None

    def restart_deployment(self, namespace, name, restarted_at):
        patch = {
            "spec": {"template": {"metadata": {"annotations": {RESTART_ANNOTATION: restarted_at}}}}
        }
        request = urllib.request.Request(
            f"{self.api_url}/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
            data=json.dumps(patch).encode(),
            method="PATCH",
            headers={"Content-Type": "application/strategic-merge-patch+json"},
        )
        if os.path.exists(self.token_path):
            with open(self.token_path, encoding="utf-8") as token_file:
                request.add_header("Authorization", "Bearer " + token_file.read().strip())

        # A URL vem da configuração do operador e o esquema é validado em Config.validate.
        with urllib.request.urlopen(request, timeout=10, context=self.context) as response:  # nosec B310
            return response.status


class Healer:
    def __init__(self, config, kubernetes, clock=time.monotonic):
        self.config = config
        self.kubernetes = kubernetes
        self.clock = clock
        self.last_restart = {}
        self.lock = threading.Lock()

    def handle_notification(self, payload):
        """Processa uma notificação do Grafana e devolve as ações tomadas por alerta."""
        results = []
        for alert in payload.get("alerts", []):
            labels = alert.get("labels", {})
            deployment = labels.get("deployment") or labels.get("service", "")
            alertname = labels.get("alertname", "")

            if alert.get("status") != "firing":
                results.append(self._skip(alertname, deployment, "alerta não está em firing"))
                continue
            if deployment not in self.config.allowed:
                results.append(self._skip(alertname, deployment, "Deployment fora da lista permitida"))
                continue
            results.append(self._restart(alertname, deployment))
        return results

    def _skip(self, alertname, deployment, reason):
        event(logging.INFO, "ação ignorada", alertname=alertname, deployment=deployment, reason=reason)
        return {"deployment": deployment, "action": "skipped", "reason": reason}

    def _restart(self, alertname, deployment):
        with self.lock:
            now = self.clock()
            last = self.last_restart.get(deployment)
            if last is not None and now - last < self.config.cooldown_seconds:
                remaining = int(self.config.cooldown_seconds - (now - last))
                return self._skip(alertname, deployment, f"cooldown ativo ({remaining}s restantes)")
            self.last_restart[deployment] = now

        restarted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fields = {
            "alertname": alertname,
            "namespace": self.config.namespace,
            "deployment": deployment,
            "restarted_at": restarted_at,
        }

        if self.config.dry_run:
            event(logging.WARNING, "rollout restart simulado (DRY_RUN)", **fields)
            return {"deployment": deployment, "action": "dry-run"}

        event(logging.WARNING, "executando rollout restart", **fields)
        try:
            status = self.kubernetes.restart_deployment(self.config.namespace, deployment, restarted_at)
        except (urllib.error.URLError, OSError) as error:
            with self.lock:
                self.last_restart.pop(deployment, None)
            event(logging.ERROR, "falha no rollout restart", error=str(error), **fields)
            return {"deployment": deployment, "action": "failed", "reason": str(error)}

        event(logging.WARNING, "rollout restart concluído", status=status, **fields)
        return {"deployment": deployment, "action": "restarted"}


def make_handler(config, healer):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self._reply(200, {"status": "ok"})
            else:
                self._reply(404, {"error": "não encontrado"})

        def do_POST(self):
            if self.path != "/webhook":
                self._reply(404, {"error": "não encontrado"})
                return

            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {config.token}".encode()):
                event(logging.WARNING, "webhook rejeitado: token inválido", client=self.client_address[0])
                self._reply(401, {"error": "não autorizado"})
                return

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_BYTES:
                self._reply(400, {"error": "corpo inválido"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._reply(400, {"error": "JSON inválido"})
                return

            event(
                logging.INFO,
                "webhook recebido",
                status=payload.get("status"),
                alerts=len(payload.get("alerts", [])),
            )
            self._reply(200, {"results": healer.handle_notification(payload)})

        def log_message(self, format, *args):
            # Os logs de acesso padrão saem em stderr sem estrutura; o app já registra os eventos relevantes.
            return

        def _reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main():
    configure_logging()
    config = Config()
    errors = config.validate()
    if errors:
        for error in errors:
            event(logging.CRITICAL, error)
        return 1

    healer = Healer(config, KubernetesClient(config.api_url))
    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(config, healer))  # nosec B104
    event(
        logging.INFO,
        "Self-Healing iniciado",
        port=config.port,
        namespace=config.namespace,
        allowed=sorted(config.allowed),
        dry_run=config.dry_run,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
