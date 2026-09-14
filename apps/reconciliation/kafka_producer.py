"""Publish reconciliation outcomes to Kafka (Phase 5A: record.matched)."""

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
                "client.id": "reconciliation-match",
            }
        )
        _producer_bootstrap = servers
    return _producer


def publish_record_matched(payload: dict[str, Any]) -> None:
    if not getattr(settings, "KAFKA_ENABLED", True):
        return

    topic = getattr(settings, "KAFKA_TOPIC_RECORD_MATCHED", "record.matched")
    body = {
        "event": "record.matched",
        "project_id": payload.get("project_id"),
        "run_id": payload.get("run_id"),
        "matched_pairs": payload.get("matched_pairs"),
        "match_result_ids": payload.get("match_result_ids") or [],
    }
    key = str(body.get("run_id") or "").encode("utf-8")
    value = json.dumps(body).encode("utf-8")

    try:
        producer = _get_producer()
        producer.produce(topic, key=key, value=value)
        producer.flush(timeout=10)
        logger.info(
            "Published %s to %s (run_id=%s, pairs=%s)",
            body["event"],
            topic,
            body["run_id"],
            body["matched_pairs"],
        )
    except Exception:
        logger.exception("Failed to publish record.matched for run_id=%s", body.get("run_id"))
