"""
Celery job: run ingest_source in a worker, not in the HTTP request.

Broker (Redis) holds pending messages. The worker pulls one, calls this
function, then stores the return value on the result backend (also Redis).

A second POST enqueues a second job — duplicate rows unless the client does
not retry 202, or we add a UniqueConstraint later.
"""

from pathlib import Path

from celery import shared_task

from apps.adaptors.registry import get_adapter
from apps.ingestion.services import ingest_source, persist_upload


@shared_task
def ingest_file_task(source_type: str, source_id: str, file_path: str) -> dict:
    try:
        return ingest_source(source_type, source_id, file_path)
    finally:
        Path(file_path).unlink(missing_ok=True)


def enqueue_ingest_file(source_type: str, source_id: str, uploaded_file):
    """
    Validate adapter, save bytes, put JSON-safe args on the broker.

    Unknown source_type fails here (HTTP 400) so we never write a file or
    enqueue. CSV/parse errors happen in the worker and fail the task.
    """
    get_adapter(source_type)
    path = persist_upload(uploaded_file)
    return ingest_file_task.delay(source_type, source_id, str(path))
