"""
Poll record.ingested. This is a long-lived process, not a Celery task.

Phase 5 will run match strategies here. For now we only log, so you can prove
the topic works (Kafka UI + this command) without coupling ingest to matching.
"""

from __future__ import annotations

import json
import logging
import signal
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_running = True


def _stop(*_args) -> None:
    global _running
    _running = False


def handle_record_ingested(payload: dict[str, Any]) -> None:
    """Hook for Phase 5 (reconciliation). Duplicate events are possible."""
    logger.info(
        "record.ingested source_id=%s type=%s raw=%s txns=%s ids=%s",
        payload.get("source_id"),
        payload.get("source_type"),
        payload.get("raw_count"),
        payload.get("transaction_count"),
        len(payload.get("transaction_ids") or []),
    )


def consume_ingestion_events() -> None:
    from confluent_kafka import Consumer, KafkaException

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "reconciliation-ingestion",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    topic = settings.KAFKA_TOPIC_RECORD_INGESTED
    consumer.subscribe([topic])
    logger.info("Consuming %s at %s", topic, settings.KAFKA_BOOTSTRAP_SERVERS)

    try:
        while _running:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            payload = json.loads(msg.value().decode("utf-8"))
            handle_record_ingested(payload)
    finally:
        consumer.close()
