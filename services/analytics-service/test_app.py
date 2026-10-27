import json
import os
import unittest
from types import SimpleNamespace

os.environ["ANALYTICS_WORKER_ENABLED"] = "false"

import app as analytics_app


class FakeQueueClient:
    def __init__(self):
        self.deleted = []

    def delete_message(self, queue_id, receipt):
        self.deleted.append((queue_id, receipt))


class FakeNosqlClient:
    def __init__(self):
        self.updates = []

    def update_row(self, table, details):
        self.updates.append((table, details))


class ProcessMessageTests(unittest.TestCase):
    def setUp(self):
        analytics_app.OCI_QUEUE_OCID = "ocid1.queue.test"
        analytics_app.OCI_NOSQL_TABLE = "ToggleMasterAnalytics"
        analytics_app.OCI_COMPARTMENT_OCID = "ocid1.compartment.test"
        self.queue = FakeQueueClient()
        self.nosql = FakeNosqlClient()

    def test_persists_event_before_acknowledging_message(self):
        message = SimpleNamespace(
            id=123,
            receipt="receipt-123",
            content=json.dumps(
                {
                    "user_id": "user-1",
                    "flag_name": "new-checkout",
                    "result": True,
                    "timestamp": "2026-07-09T12:00:00Z",
                }
            ),
        )

        processed = analytics_app.process_message(message, self.queue, self.nosql)

        self.assertTrue(processed)
        self.assertEqual(self.queue.deleted, [("ocid1.queue.test", "receipt-123")])
        self.assertEqual(len(self.nosql.updates), 1)
        table, details = self.nosql.updates[0]
        self.assertEqual(table, "ToggleMasterAnalytics")
        self.assertEqual(details.value["event_id"], "123")
        self.assertEqual(details.value["occurred_at"], "2026-07-09T12:00:00Z")
        self.assertEqual(details.value["result"], True)

    def test_does_not_acknowledge_invalid_event(self):
        message = SimpleNamespace(
            id="bad-event",
            receipt="receipt-bad",
            content=json.dumps({"user_id": "user-1"}),
        )

        processed = analytics_app.process_message(message, self.queue, self.nosql)

        self.assertFalse(processed)
        self.assertEqual(self.queue.deleted, [])
        self.assertEqual(self.nosql.updates, [])


class TraceContextTests(unittest.TestCase):
    def test_consumer_span_continues_producer_trace(self):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        analytics_app.tracer = provider.get_tracer("test")

        traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        message = SimpleNamespace(
            id="traced-event",
            receipt="receipt-traced",
            content=json.dumps({"user_id": "user-1", "trace_context": {"traceparent": traceparent}}),
        )

        analytics_app.process_message(message, FakeQueueClient(), FakeNosqlClient())

        (span,) = exporter.get_finished_spans()
        self.assertEqual(span.kind, trace.SpanKind.CONSUMER)
        self.assertEqual(format(span.context.trace_id, "032x"), "0af7651916cd43dd8448eb211c80319c")
        self.assertEqual(format(span.parent.span_id, "016x"), "b7ad6b7169203331")

    def test_message_without_trace_context_starts_new_trace(self):
        message = SimpleNamespace(id="plain", receipt="r", content="{}")
        self.assertEqual(analytics_app.message_trace_context(message), {})


if __name__ == "__main__":
    unittest.main()
