"""
Celery job: run ingest_source in a worker, not in the HTTP request.

Broker (Redis) holds pending messages. The worker pulls one, calls this
function, then stores the return value on the result backend (also Redis).
"""

import logging
from pathlib import Path

from celery import shared_task

from apps.adaptors.registry import get_adapter
from apps.ingestion.models import IngestFile, MappingTemplate
from apps.ingestion.services import ingest_source, stage_uploaded_file

logger = logging.getLogger(__name__)


def _store_ingest_error(ingest_file: IngestFile, exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    ingest_file.status = IngestFile.Status.ERROR
    ingest_file.error_message = message[:4000]
    ingest_file.save(update_fields=["status", "error_message", "updated_at"])
    return ingest_file.error_message


@shared_task
def ingest_file_task(ingest_file_id: int, template_id: int | None = None) -> dict:
    ingest_file = IngestFile.objects.get(pk=ingest_file_id)
    ingest_file.status = IngestFile.Status.INGESTING
    ingest_file.error_message = ""
    ingest_file.save(update_fields=["status", "error_message", "updated_at"])
    template = (
        MappingTemplate.objects.prefetch_related("columns").get(pk=template_id)
        if template_id
        else None
    )
    path = Path(ingest_file.path)
    try:
        if not path.is_file():
            raise ValueError(
                "Staged file is missing on disk. Upload the file again "
                "(successful ingest deletes the staged copy to avoid duplicate loads)."
            )
        result = ingest_source(
            ingest_file.source_type,
            ingest_file.source_id,
            str(path),
            template=template,
            ingest_file=ingest_file,
        )
        ingest_file.status = IngestFile.Status.DONE
        ingest_file.save(update_fields=["status", "updated_at"])
        path.unlink(missing_ok=True)
        return result
    except Exception as exc:
        message = _store_ingest_error(ingest_file, exc)
        logger.error("Ingest failed for file_id=%s: %s", ingest_file_id, message)
        return {"ok": False, "error": message}


def enqueue_ingest_file(source_type: str, source_id: str, uploaded_file, template_id: int | None = None):
    """
    Validate adapter, stage bytes as IngestFile, put JSON-safe ids on the broker.

    API / tests call this without a template (heuristic tabular normalize).
    Mapping studio passes template_id after the operator maps columns.
    """
    get_adapter(source_type)
    ingest_file = stage_uploaded_file(uploaded_file, source_type, source_id)
    return ingest_file_task.delay(ingest_file.id, template_id)
