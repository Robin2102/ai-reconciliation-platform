"""
Celery jobs: ingestion job runs (merged multi-file ingest).
"""

import logging

from celery import shared_task
from django.utils import timezone

from apps.ingestion.job_services import execute_ingestion_job_run
from apps.ingestion.models import IngestionJobRun

logger = logging.getLogger(__name__)


@shared_task
def ingestion_job_run_task(run_id: int) -> dict:
    run = IngestionJobRun.objects.select_related("job__connector", "job__template").get(pk=run_id)
    run.status = IngestionJobRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error_message = ""
    run.save(update_fields=["status", "started_at", "error_message"])
    try:
        stats = execute_ingestion_job_run(run)
        run.stats = stats
        if stats.get("errors"):
            run.status = IngestionJobRun.Status.ERROR
            run.error_message = f"{len(stats['errors'])} file(s) had errors (partial ingest may have run)."
        else:
            run.status = IngestionJobRun.Status.DONE
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "status", "error_message", "finished_at"])
        return {"ok": True, "run_id": run_id, **stats}
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        run.status = IngestionJobRun.Status.ERROR
        run.error_message = message[:4000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
        logger.error("Ingestion job run %s failed: %s", run_id, message)
        return {"ok": False, "error": message}
