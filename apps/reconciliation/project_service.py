"""Create and validate reconciliation projects (Phase 5A)."""

from __future__ import annotations

from apps.ingestion.models import IngestFile
from apps.reconciliation.leg_data import leg_row_count
from apps.reconciliation.recon_models import ReconLeg, ReconProject
from apps.reconciliation.rules_defaults import seed_default_rules


def create_recon_project(
    name: str,
    description: str,
    source_ingest_id: int,
    target_ingest_id: int,
) -> ReconProject:
    if source_ingest_id == target_ingest_id:
        raise ValueError("Source and target must be two different completed ingests.")

    source_file = IngestFile.objects.get(pk=source_ingest_id)
    target_file = IngestFile.objects.get(pk=target_ingest_id)

    for label, ingest in (("Source", source_file), ("Target", target_file)):
        if ingest.status != IngestFile.Status.DONE:
            raise ValueError(f"{label} ingest must be done before reconciliation.")

    project = ReconProject.objects.create(
        name=name.strip(),
        description=(description or "").strip(),
        status=ReconProject.Status.READY,
    )
    ReconLeg.objects.create(
        project=project,
        role=ReconLeg.Role.SOURCE,
        ingest_file=source_file,
        feed_key=source_file.source_id,
        row_count=leg_row_count(source_file),
    )
    ReconLeg.objects.create(
        project=project,
        role=ReconLeg.Role.TARGET,
        ingest_file=target_file,
        feed_key=target_file.source_id,
        row_count=leg_row_count(target_file),
    )
    seed_default_rules(project)
    return project
