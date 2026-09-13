"""
Repository-shaped ingest pipeline: adapter → staging → canonical.

The DRF view must stay thin. Celery (Phase 3) will call this same function
from a worker; do not duplicate this logic in tasks.py later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Union

from django.db import transaction

from apps.adaptors.registry import get_adapter
from apps.ingestion.models import RawRecord
from apps.reconciliation.models import save_canonical_records

SourceInput = Union[str, Path, bytes, BinaryIO]


def ingest_source(
    source_type: str,
    source_id: str,
    source_input: SourceInput,
) -> dict[str, Any]:
    """
    Extract raw rows, persist them for audit, normalize, persist Transactions.

    Raises ValueError for unknown adapters / empty files.
    Raises pydantic.ValidationError if a row cannot become a CanonicalRecord.
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


def ingest_upload(source_type: str, source_id: str, uploaded_file) -> dict[str, Any]:
    """Read an uploaded file into bytes, then ingest. Used by the DRF view."""
    payload = uploaded_file.read()
    if not payload:
        raise ValueError("Uploaded file is empty.")
    return ingest_source(source_type, source_id, payload)