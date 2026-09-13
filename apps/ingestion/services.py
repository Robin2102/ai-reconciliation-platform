"""
Ingest pipeline: adapter → staging → canonical.

HTTP/admin only persist the file and enqueue. parse+insert stays here so the
Celery worker and tests call the same function.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Union
from uuid import uuid4

from django.conf import settings
from django.db import transaction

from apps.adaptors.registry import get_adapter
from apps.ingestion.models import RawRecord
from apps.reconciliation.models import save_canonical_records

SourceInput = Union[str, Path, bytes, BinaryIO]


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


def ingest_source(
    source_type: str,
    source_id: str,
    source_input: SourceInput,
) -> dict[str, Any]:
    """
    Extract raw rows, persist them for audit, normalize, persist Transactions.

    Raises ValueError for unknown adapters / empty files.
    Raises pydantic.ValidationError if a row cannot become a CanonicalRecord.

    Double upload of the same file currently inserts a second copy. A later
    UniqueConstraint on Transaction (source_id, external_ref) can reject or skip
    duplicates; do not retry a 202 blindly.
    """
    adapter_cls = get_adapter(source_type)
    adapter = adapter_cls()
    raw_rows = list(adapter.extract(source_input))
    if not raw_rows:
        raise ValueError("No rows extracted from the source.")

    canonical_records = [
        adapter.normalize(row, source_id=source_id) for row in raw_rows
    ]

    raw_instances = [
        RawRecord(
            source_type=source_type.lower(),
            source_id=source_id,
            raw_payload=row,
            status="NORMALIZED",
        )
        for row in raw_rows
    ]

    with transaction.atomic():
        created_raw = RawRecord.objects.bulk_create(raw_instances, batch_size=1000)
        created_tx = save_canonical_records(canonical_records)

    return {
        "source_type": source_type.lower(),
        "source_id": source_id,
        "raw_count": len(created_raw),
        "transaction_count": len(created_tx),
    }
