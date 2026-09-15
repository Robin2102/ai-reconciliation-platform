"""Merge multiple job files into one ingestion (single publish, filename per row)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.adaptors.registry import get_adapter
from apps.ingestion.job_inputs import materialize_job_input, max_job_input_files
from apps.ingestion.kafka_producer import publish_record_ingested
from apps.ingestion.mapping import apply_column_mapping, validate_template
from apps.ingestion.models import IngestionJob, IngestionJobRun, IngestFile, RawRecord
from apps.ingestion.services import NO_DATA_ROWS_MESSAGE, profiler_source_type
from apps.reconciliation.models import save_canonical_records


def execute_merged_ingestion_run(run: IngestionJobRun) -> dict[str, Any]:
    job = run.job
    template = job.template
    if template is None:
        raise ValueError("Map columns before running the job (Mapping / profile step).")

    columns = list(template.columns.all())
    validate_template(template, columns=columns)

    inputs = list(job.inputs.filter(enabled=True).order_by("order", "id"))
    if not inputs:
        raise ValueError("Add at least one file (upload or connector browse).")
    if len(inputs) > max_job_input_files():
        raise ValueError(f"At most {max_job_input_files()} files per job.")

    ingest_file = IngestFile.objects.create(
        path="merged",
        original_name=f"{job.name} ({len(inputs)} files)",
        source_type=job.default_source_type,
        source_id=job.source_id,
        job_run=run,
        status=IngestFile.Status.INGESTING,
    )
    run.primary_ingest_file = ingest_file

    uploaded_at = timezone.now()
    canonical_records = []
    raw_instances = []
    temp_paths: list[Path] = []
    files_ok = 0
    errors: list[dict] = []

    for inp in inputs:
        try:
            path, source_type, filename = materialize_job_input(job, inp)
            if inp.remote_path and not inp.local_path:
                temp_paths.append(path)
            source_type = profiler_source_type(path, source_type)
            adapter = get_adapter(source_type)()
            rows = list(adapter.extract(path))
            if not rows:
                raise ValueError(NO_DATA_ROWS_MESSAGE)
            for row in rows:
                rec = apply_column_mapping(
                    row,
                    template,
                    job.source_id,
                    columns=columns,
                    uploaded_at=uploaded_at,
                    source_filename=filename,
                )
                canonical_records.append(rec)
                raw_instances.append(
                    RawRecord(
                        source_type=source_type.lower(),
                        source_id=job.source_id,
                        raw_payload=rec.raw_payload,
                        status="NORMALIZED",
                        ingest_file=ingest_file,
                    )
                )
            files_ok += 1
        except Exception as exc:
            errors.append({"file": inp.original_filename or inp.remote_path, "error": str(exc)})

    if not canonical_records:
        ingest_file.status = IngestFile.Status.ERROR
        ingest_file.error_message = "No rows extracted from any file."
        ingest_file.save(update_fields=["status", "error_message", "updated_at"])
        run.save(update_fields=["primary_ingest_file"])
        for p in temp_paths:
            p.unlink(missing_ok=True)
        raise ValueError(ingest_file.error_message)

    with transaction.atomic():
        RawRecord.objects.bulk_create(raw_instances, batch_size=1000)
        created_tx = save_canonical_records(canonical_records, ingest_file=ingest_file)

    ingest_file.status = IngestFile.Status.DONE
    ingest_file.path = str(temp_paths[0]) if len(temp_paths) == 1 else "merged"
    ingest_file.save(update_fields=["status", "path", "updated_at"])
    run.save(update_fields=["primary_ingest_file"])

    for p in temp_paths:
        p.unlink(missing_ok=True)

    result = {
        "source_type": job.default_source_type,
        "source_id": job.source_id,
        "raw_count": len(raw_instances),
        "transaction_count": len(created_tx),
        "transaction_ids": [tx.pk for tx in created_tx if tx.pk is not None],
        "ingest_file_id": ingest_file.pk,
    }
    publish_record_ingested(result)

    job.last_run_at = timezone.now()
    job.status = IngestionJob.Status.READY
    job.save(update_fields=["last_run_at", "status"])

    return {
        "files_total": len(inputs),
        "files_ok": files_ok,
        "transaction_count": len(created_tx),
        "ingest_file_id": ingest_file.pk,
        "errors": errors,
    }
