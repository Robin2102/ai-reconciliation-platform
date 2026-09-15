"""
Publish facts to Kafka after ingest commits.

Celery: ingestion job run (merged ingest). Kafka: "records were ingested" — recon, metrics,
or an AI service can subscribe without changing the Celery task.

Payload is identifiers and counts, never the CSV or raw_payload (those live in
Postgres). Kafka delivers at-least-once: a consumer may see the same event twice.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_producer = None
_producer_bootstrap = None


def _get_producer():
    global _producer, _producer_bootstrap
    servers = settings.KAFKA_BOOTSTRAP_SERVERS
    if _producer is None or _producer_bootstrap != servers:
        from confluent_kafka import Producer

        _producer = Producer(
            {
                "bootstrap.servers": servers,
                "client.id": "reconciliation-ingest",
            }
        )
        _producer_bootstrap = servers
    return _producer


def publish_record_ingested(payload: dict[str, Any]) -> None:
    if not getattr(settings, "KAFKA_ENABLED", True):
        return

    topic = settings.KAFKA_TOPIC_RECORD_INGESTED
    body = {
        "event": "record.ingested",
        "source_type": payload.get("source_type"),
        "source_id": payload.get("source_id"),
        "raw_count": payload.get("raw_count"),
        "transaction_count": payload.get("transaction_count"),
        "transaction_ids": payload.get("transaction_ids") or [],
    }
    key = (body["source_id"] or "").encode("utf-8")
    value = json.dumps(body).encode("utf-8")

    try:
        producer = _get_producer()
        producer.produce(topic, key=key, value=value)
        producer.flush(timeout=10)
        logger.info(
            "Published %s to %s (source_id=%s, transactions=%s)",
            body["event"],
            topic,
            body["source_id"],
            body["transaction_count"],
        )
    except Exception:
        # Ingest already committed. Do not delete rows; log so ops can replay.
        logger.exception("Failed to publish record.ingested for source_id=%s", body["source_id"])
