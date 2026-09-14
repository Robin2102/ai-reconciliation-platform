"""
Ingest pipeline: adapter → staging → canonical.

HTTP/admin only persist the file and enqueue. parse+insert stays here so the
Celery worker and tests call the same function.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Optional, Union
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_tz

from apps.adaptors.registry import get_adapter
from apps.ingestion.kafka_producer import publish_record_ingested
from apps.ingestion.mapping import apply_column_mapping, validate_template
from apps.ingestion.models import IngestFile, MappingTemplate, RawRecord
from apps.reconciliation.models import save_canonical_records

SourceInput = Union[str, Path, bytes, BinaryIO]

_TXT_EXTENSIONS = {".txt", ".text"}

NO_DATA_ROWS_MESSAGE = (
    "No data rows found in the file. Add at least one row below the header, use a delimited "
    "text format (comma, semicolon, tab, or pipe), and save as UTF-8. Fixed-width .txt is not "
    "supported yet."
)


def infer_source_type(filename: str, source_type: str | None = None) -> str:
    """
    Pick adapter key from extension when ops leaves the default csv.

    Explicit non-csv source_type (e.g. txt) is respected.
    """
    explicit = (source_type or "csv").strip().lower()
    ext = Path(filename or "").suffix.lower()
    if explicit != "csv":
        return explicit
    if ext in _TXT_EXTENSIONS:
        return "txt"
    return "csv"


def count_extracted_rows(source_type: str, source_input: SourceInput) -> int:
    """How many data rows the adapter would yield (header row is not counted)."""
    adapter_cls = get_adapter(source_type)
    return sum(1 for _ in adapter_cls().extract(source_input))


def persist_upload(uploaded_file, dest_dir: Path | None = None) -> Path:
    """
    Write the Django upload to disk so Celery can receive a JSON-safe path.

    Celery cannot serialize InMemoryUploadedFile; the worker is a second process
    and would not see that object anyway.
    """
    payload = uploaded_file.read()
    if not payload:
        raise ValueError("Uploaded file is empty.")

    dest = Path(dest_dir or settings.INGEST_UPLOAD_DIR)
    dest.mkdir(parents=True, exist_ok=True)
    suffix = Path(getattr(uploaded_file, "name", "") or "upload.csv").suffix or ".csv"
    path = dest / f"{uuid4().hex}{suffix}"
    path.write_bytes(payload)
    return path


def stage_uploaded_file(uploaded_file, source_type: str, source_id: str) -> IngestFile:
    get_adapter(source_type)
    path = persist_upload(uploaded_file)
    if count_extracted_rows(source_type, path) == 0:
        path.unlink(missing_ok=True)
        raise ValueError(NO_DATA_ROWS_MESSAGE)
    return IngestFile.objects.create(
        path=str(path),
        original_name=getattr(uploaded_file, "name", "") or path.name,
        source_type=source_type.lower(),
        source_id=source_id,
        status=IngestFile.Status.STAGED,
    )


def ingest_source(
    source_type: str,
    source_id: str,
    source_input: SourceInput,
    template: Optional[MappingTemplate] = None,
    ingest_file: Optional[IngestFile] = None,
) -> dict[str, Any]:
    """
    Extract raw rows, persist them for audit, normalize, persist Transactions.

    With a MappingTemplate, rows become CanonicalRecord via apply_column_mapping.
    Without one, CsvAdapter.normalize keeps the heuristic/legacy path.
    """
    adapter_cls = get_adapter(source_type)
    adapter = adapter_cls()
    raw_rows = list(adapter.extract(source_input))
    if not raw_rows:
        path_hint = ""
        if isinstance(source_input, (str, Path)):
            p = Path(source_input)
            if not p.exists():
                path_hint = " The staged file is missing—upload again (a previous successful ingest removes the file from disk)."
            elif p.stat().st_size == 0:
                path_hint = " The staged file on disk is empty."
        raise ValueError(NO_DATA_ROWS_MESSAGE + path_hint)

    if template is not None:
        columns = list(template.columns.all())
        validate_template(template, columns=columns)
        uploaded_at = ingest_file.created_at if ingest_file is not None else dj_tz.now()
        canonical_records = [
            apply_column_mapping(
                row,
                template,
                source_id=source_id,
                columns=columns,
                uploaded_at=uploaded_at,
            )
            for row in raw_rows
        ]
        stored_rows = [rec.raw_payload for rec in canonical_records]
    else:
        canonical_records = [
            adapter.normalize(row, source_id=source_id) for row in raw_rows
        ]
        stored_rows = raw_rows

    raw_instances = [
        RawRecord(
            source_type=source_type.lower(),
            source_id=source_id,
            raw_payload=payload,
            status="NORMALIZED",
        )
        for payload in stored_rows
    ]

    with transaction.atomic():
        created_raw = RawRecord.objects.bulk_create(raw_instances, batch_size=1000)
        created_tx = save_canonical_records(canonical_records)

    result = {
        "source_type": source_type.lower(),
        "source_id": source_id,
        "raw_count": len(created_raw),
        "transaction_count": len(created_tx),
        "transaction_ids": [tx.pk for tx in created_tx if tx.pk is not None],
    }
    publish_record_ingested(result)
    return result
