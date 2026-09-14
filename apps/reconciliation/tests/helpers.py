"""Shared ingest fixtures for reconciliation tests."""

from __future__ import annotations

import io

from apps.ingestion.models import IngestFile
from apps.ingestion.services import ingest_source
from apps.reconciliation.models import Transaction


def stage_done_ingest(name: str, source_id: str, body: str) -> IngestFile:
    ingest_source("csv", source_id, io.BytesIO(body.encode("utf-8")))
    ingest_file = IngestFile.objects.create(
        path="/tmp/unused",
        original_name=name,
        source_type="csv",
        source_id=source_id,
        status=IngestFile.Status.DONE,
    )
    Transaction.objects.filter(source_id=source_id).update(ingest_file=ingest_file)
    return ingest_file
