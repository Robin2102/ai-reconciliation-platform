"""Resolve ingestion job inputs (upload path or connector fetch)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings

from apps.connectors.models import Connector
from apps.ingestion.models import IngestionJob, IngestionJobInput
from apps.ingestion.services import NO_DATA_ROWS_MESSAGE, count_extracted_rows, infer_source_type, persist_upload


def max_job_input_files() -> int:
    return int(getattr(settings, "MAX_INGESTION_JOB_FILES", 5))


def _fetch_remote_to_path(connector: Connector, remote_path: str, dest: Path) -> Path:
    from apps.connectors.services import fetch_connector_file

    result = fetch_connector_file(connector, remote_path, dest)
    if not result.ok or result.local_path is None:
        raise ValueError(result.message or f"Fetch failed: {remote_path}")
    return result.local_path


def materialize_job_input(
    job: IngestionJob,
    inp: IngestionJobInput,
    *,
    persist_for_profile: bool = False,
    force_refetch: bool = False,
) -> tuple[Path, str, str]:
    """
    Return (local_path, source_type, display_filename).

    If `persist_for_profile` is False, connector files are fetched to a temp path
    that the caller should delete after use (merged ingest deletes after read).
    """
    filename = inp.original_filename or Path(inp.remote_path or inp.local_path or "data.csv").name
    source_type = infer_source_type(filename, job.default_source_type)

    if inp.local_path:
        path = Path(inp.local_path)
        if not path.is_file():
            raise ValueError(f"Missing uploaded file: {filename}")
        return path, source_type, filename

    if not inp.remote_path:
        raise ValueError(f"Input {inp.pk} has no path.")

    connector = job.connector
    if connector is None:
        raise ValueError("Job has no connector for remote paths.")

    if persist_for_profile:
        dest_dir = Path(settings.INGEST_UPLOAD_DIR) / "job_profile" / str(job.pk)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        if dest.is_file() and not force_refetch:
            return dest, infer_source_type(filename, job.default_source_type), filename
        if dest.is_file():
            dest.unlink(missing_ok=True)
        path = _fetch_remote_to_path(connector, inp.remote_path, dest)
        return path, infer_source_type(filename, job.default_source_type), filename

    dest_dir = Path(settings.INGEST_UPLOAD_DIR) / "job_fetch"
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".csv"
    dest = dest_dir / f"{uuid4().hex}{suffix}"
    path = _fetch_remote_to_path(connector, inp.remote_path, dest)
    return path, source_type, filename


def persist_uploads_to_job_inputs(job: IngestionJob, uploaded_files) -> int:
    count = 0
    for upload in uploaded_files:
        path = persist_upload(upload)
        source_type = infer_source_type(getattr(upload, "name", "") or path.name, job.default_source_type)
        if count_extracted_rows(source_type, path) == 0:
            path.unlink(missing_ok=True)
            raise ValueError(NO_DATA_ROWS_MESSAGE)
        IngestionJobInput.objects.create(
            job=job,
            order=job.inputs.count(),
            local_path=str(path),
            original_filename=getattr(upload, "name", path.name) or path.name,
        )
        count += 1
    return count


def clear_job_profile_cache(job: IngestionJob) -> None:
    profile_dir = Path(settings.INGEST_UPLOAD_DIR) / "job_profile" / str(job.pk)
    if profile_dir.is_dir():
        for cached in profile_dir.iterdir():
            if cached.is_file():
                cached.unlink(missing_ok=True)
    job.profile_local_path = ""
    job.save(update_fields=["profile_local_path"])


def ensure_job_profile_file(job: IngestionJob) -> None:
    inp = job.inputs.filter(enabled=True).order_by("order", "id").first()
    if inp is None:
        raise ValueError("Add at least one file to the job before profiling.")
    if job.profile_local_path and Path(job.profile_local_path).is_file():
        return
    path, source_type, _ = materialize_job_input(job, inp, persist_for_profile=True)
    job.profile_local_path = str(path)
    job.default_source_type = source_type
    job.save(update_fields=["profile_local_path", "default_source_type"])


def refresh_job_profile_file(job: IngestionJob) -> str:
    """Re-fetch the first job input from disk/connector and re-detect columns."""
    inp = job.inputs.filter(enabled=True).order_by("order", "id").first()
    if inp is None:
        raise ValueError("Add at least one file to the job before profiling.")
    clear_job_profile_cache(job)
    path, source_type, filename = materialize_job_input(
        job, inp, persist_for_profile=True, force_refetch=True
    )
    job.profile_local_path = str(path)
    job.default_source_type = source_type
    job.save(update_fields=["profile_local_path", "default_source_type"])
    return filename


def infer_default_source_type_from_inputs(
    uploaded_files,
    remote_paths: list[str],
    *,
    fallback: str = "csv",
) -> str:
    names: list[str] = [getattr(f, "name", "") for f in uploaded_files if getattr(f, "name", None)]
    names.extend(Path(p).name for p in remote_paths if p)
    if not names:
        return fallback
    return infer_source_type(names[0], fallback)
