import json
import logging
import os
import sys
import threading
import time

import oci
from dotenv import load_dotenv
from flask import Flask, jsonify
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Logs no stdout. Com OpenTelemetry ativo, o handler OTLP já está na raiz e
# basicConfig seria ignorado, por isso o handler de console é adicionado explicitamente.
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
logging.getLogger().addHandler(_console)
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

load_dotenv()

WORKER_ENABLED = os.getenv("ANALYTICS_WORKER_ENABLED", "true").lower() not in (
    "0",
    "false",
    "no",
)
OCI_REGION = os.getenv("OCI_REGION")
OCI_QUEUE_OCID = os.getenv("OCI_QUEUE_OCID")
OCI_QUEUE_MESSAGES_ENDPOINT = os.getenv("OCI_QUEUE_MESSAGES_ENDPOINT")
OCI_NOSQL_TABLE = os.getenv("OCI_NOSQL_TABLE")
OCI_COMPARTMENT_OCID = os.getenv("OCI_COMPARTMENT_OCID")
OCI_AUTH_MODE = os.getenv("OCI_AUTH_MODE", "workload_identity").lower()
ANALYTICS_QUEUE_NAME = "togglemaster-analytics"

tracer = trace.get_tracer("analytics-service")


def validate_worker_configuration():
    required = {
        "OCI_REGION": OCI_REGION,
        "OCI_QUEUE_OCID": OCI_QUEUE_OCID,
        "OCI_QUEUE_MESSAGES_ENDPOINT": OCI_QUEUE_MESSAGES_ENDPOINT,
        "OCI_NOSQL_TABLE": OCI_NOSQL_TABLE,
    }
    missing = [name for name, value in required.items() if not value]

    if (
        OCI_NOSQL_TABLE
        and not OCI_NOSQL_TABLE.startswith("ocid1.nosqltable.")
        and not OCI_COMPARTMENT_OCID
    ):
        missing.append("OCI_COMPARTMENT_OCID (required when OCI_NOSQL_TABLE is a name)")

    if missing:
        raise ValueError("Missing OCI configuration: " + ", ".join(missing))


def configuration_and_signer():
    if OCI_AUTH_MODE == "workload_identity":
        signer = oci.auth.signers.get_oke_workload_identity_resource_principal_signer()
        return {"region": OCI_REGION}, signer

    if OCI_AUTH_MODE == "instance_principal":
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        return {"region": OCI_REGION}, signer

    if OCI_AUTH_MODE == "config_file":
        config_file = os.getenv("OCI_CONFIG_FILE", oci.config.DEFAULT_LOCATION)
        profile = os.getenv("OCI_CONFIG_PROFILE", oci.config.DEFAULT_PROFILE)
        config = oci.config.from_file(config_file, profile)
        if OCI_REGION:
            config["region"] = OCI_REGION
        return config, None

    raise ValueError(
        "OCI_AUTH_MODE must be workload_identity, instance_principal, or config_file"
    )


def build_oci_clients():
    config, signer = configuration_and_signer()
    auth_options = {"signer": signer} if signer else {}

    queue = oci.queue.QueueClient(
        config,
        service_endpoint=OCI_QUEUE_MESSAGES_ENDPOINT.rstrip("/"),
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY,
        **auth_options,
    )
    nosql = oci.nosql.NosqlClient(
        config,
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY,
        **auth_options,
    )
    return queue, nosql


queue_client = None
nosql_client = None

if WORKER_ENABLED:
    try:
        validate_worker_configuration()
        queue_client, nosql_client = build_oci_clients()
        log.info("OCI Queue and NoSQL clients initialized in region %s", OCI_REGION)
    except Exception:
        log.exception("Unable to initialize OCI clients")
        sys.exit(1)
else:
    log.info("Analytics worker disabled for local execution.")


def message_trace_context(message):
    """Extract the producer trace context sent by evaluation-service in the message metadata."""
    metadata = getattr(message, "metadata", None)
    properties = getattr(metadata, "custom_properties", None) or {}
    return propagate.extract(properties)


def process_message(message, queue=None, nosql=None):
    """Process one OCI Queue message as a consumer span linked to the producer trace."""
    with tracer.start_as_current_span(
        f"process {ANALYTICS_QUEUE_NAME}",
        context=message_trace_context(message),
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "oci_queue",
            "messaging.destination.name": ANALYTICS_QUEUE_NAME,
            "messaging.operation.type": "process",
            "messaging.message.id": str(message.id),
        },
    ) as span:
        processed = _store_message(message, queue, nosql)
        if not processed:
            span.set_status(Status(StatusCode.ERROR, "message not processed"))
        return processed


def _store_message(message, queue=None, nosql=None):
    """Persist one OCI Queue message in NoSQL, then acknowledge it."""
    queue = queue or queue_client
    nosql = nosql or nosql_client
    message_id = str(message.id)

    try:
        log.info("Processing OCI Queue message ID: %s", message_id)
        body = json.loads(message.content)

        required_fields = ("user_id", "flag_name", "result", "timestamp")
        missing_fields = [field for field in required_fields if field not in body]
        if missing_fields:
            raise ValueError("missing event fields: " + ", ".join(missing_fields))
        if not isinstance(body["result"], bool):
            raise TypeError("event field result must be a boolean")

        row = {
            "event_id": message_id,
            "user_id": str(body["user_id"]),
            "flag_name": str(body["flag_name"]),
            "result": body["result"],
            "occurred_at": str(body["timestamp"]),
        }
        details = {"value": row}
        if OCI_COMPARTMENT_OCID:
            details["compartment_id"] = OCI_COMPARTMENT_OCID

        nosql.update_row(
            OCI_NOSQL_TABLE,
            oci.nosql.models.UpdateRowDetails(**details),
        )
        queue.delete_message(OCI_QUEUE_OCID, message.receipt)

        log.info("Event %s (flag: %s) stored in OCI NoSQL.", message_id, row["flag_name"])
        return True
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        log.error("Invalid analytics event %s: %s", message_id, error)
    except oci.exceptions.ServiceError as error:
        log.error("OCI error while processing message %s: %s", message_id, error)
    except Exception:
        log.exception("Unexpected error while processing message %s", message_id)

    # The message is deliberately not acknowledged so OCI Queue can redeliver it.
    return False


def queue_worker_loop():
    log.info("Starting OCI Queue analytics worker...")
    while True:
        try:
            response = queue_client.get_messages(
                OCI_QUEUE_OCID,
                limit=10,
                visibility_in_seconds=30,
                timeout_in_seconds=20,
            )
            messages = response.data.messages
            if not messages:
                continue

            log.info("Received %d OCI Queue messages.", len(messages))
            for message in messages:
                process_message(message)
        except oci.exceptions.ServiceError as error:
            log.error("OCI Queue worker error: %s", error)
            time.sleep(10)
        except Exception:
            log.exception("Unexpected analytics worker error")
            time.sleep(10)


app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "worker_enabled": WORKER_ENABLED,
            "provider": "oci" if WORKER_ENABLED else "disabled",
        }
    )


def start_worker():
    if not WORKER_ENABLED:
        return

    worker_thread = threading.Thread(target=queue_worker_loop, daemon=True)
    worker_thread.start()


start_worker()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8005"))
    app.run(host="0.0.0.0", port=port, debug=False)  # nosec B104
