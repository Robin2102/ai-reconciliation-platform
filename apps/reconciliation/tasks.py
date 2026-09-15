"""Celery: run reconciliation in a worker."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.reconciliation.engine.rule_runner import run_reconciliation
from apps.reconciliation.kafka_producer import publish_record_matched
from apps.reconciliation.recon_models import ReconProject, ReconRun

logger = logging.getLogger(__name__)


@shared_task
def recon_run_task(run_id: int) -> dict:
    run = ReconRun.objects.select_related("project").get(pk=run_id)
    project = run.project
    run.status = ReconRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error_message = ""
    run.save(update_fields=["status", "started_at", "error_message"])

    project.status = ReconProject.Status.RUNNING
    project.save(update_fields=["status", "updated_at"])

    try:
        stats = run_reconciliation(run)
        run.stats = stats
        run.status = ReconRun.Status.DONE
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "status", "finished_at"])

        project.status = ReconProject.Status.DONE
        project.save(update_fields=["status", "updated_at"])

        result_ids = list(run.results.values_list("id", flat=True))
        publish_record_matched(
            {
                "project_id": project.pk,
                "run_id": run.pk,
                "matched_pairs": stats.get("matched_pairs"),
                "match_result_ids": result_ids,
            }
        )
        return {"ok": True, "run_id": run.pk, **stats}
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        run.status = ReconRun.Status.ERROR
        run.error_message = message[:4000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
        project.status = ReconProject.Status.ERROR
        project.save(update_fields=["status", "updated_at"])
        logger.error("Recon run %s failed: %s", run_id, message)
        return {"ok": False, "error": message}
