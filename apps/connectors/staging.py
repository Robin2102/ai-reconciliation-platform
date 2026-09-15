"""Fetch connector files into local staging paths."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings

from apps.connectors.models import Connector
from apps.connectors.services import fetch_connector_file
from apps.ingestion.models import IngestFile
from apps.ingestion.services import NO_DATA_ROWS_MESSAGE, count_extracted_rows, infer_source_type


def stage_connector_file(
    connector: Connector,
    remote_path: str,
    *,
    source_id: str,
    default_source_type: str = "csv",
    job_run=None,
) -> IngestFile:
    if connector is None:
        raise ValueError("Connector is required.")
    filename = Path(remote_path).name or "data.csv"
    source_type = infer_source_type(filename, default_source_type)
    dest_dir = Path(settings.INGEST_UPLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".csv"
    dest = dest_dir / f"{uuid4().hex}{suffix}"
    result = fetch_connector_file(connector, remote_path, dest)
    if not result.ok or result.local_path is None:
        raise ValueError(result.message or f"Fetch failed for {remote_path}")
    path = result.local_path
    if count_extracted_rows(source_type, path) == 0:
        path.unlink(missing_ok=True)
        raise ValueError(NO_DATA_ROWS_MESSAGE)
    return IngestFile.objects.create(
        path=str(path),
        original_name=filename,
        source_type=source_type.lower(),
        source_id=source_id,
        job_run=job_run,
        connector_fetch_path=remote_path,
        status=IngestFile.Status.STAGED,
    )
