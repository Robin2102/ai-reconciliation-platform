"""Poll record.matched — log and hook for async workflows (Phase 5B)."""

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


def handle_record_matched(payload: dict[str, Any]) -> None:
    logger.info(
        "record.matched project_id=%s run_id=%s pairs=%s result_ids=%s",
        payload.get("project_id"),
        payload.get("run_id"),
        payload.get("matched_pairs"),
        len(payload.get("match_result_ids") or []),
    )


def consume_matched_events() -> None:
    from confluent_kafka import Consumer, KafkaException

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    consumer = Consumer(
        {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "reconciliation-matched",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    topic = settings.KAFKA_TOPIC_RECORD_MATCHED
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
            handle_record_matched(payload)
    finally:
        consumer.close()
