"""Resolve normalized rows stored for an ops ingest run."""

from __future__ import annotations

import json
from datetime import timedelta

from apps.ingestion.models import IngestFile
from apps.reconciliation.models import Transaction

RESULT_ROW_LIMIT = 2000


def transactions_for_ingest_file(ingest_file: IngestFile):
    """Transactions from this upload (FK), with time-window fallback for older ingests."""
    linked = Transaction.objects.filter(ingest_file=ingest_file).order_by("-timestamp", "-id")
    if linked.exists():
        return linked
    if ingest_file.status != IngestFile.Status.DONE:
        return Transaction.objects.none()
    end = ingest_file.updated_at + timedelta(minutes=2)
    return (
        Transaction.objects.filter(
            source_id=ingest_file.source_id,
            created_at__gte=ingest_file.created_at,
            created_at__lte=end,
        )
        .order_by("-timestamp", "-id")
    )


def _display_row(tx: Transaction) -> dict:
    generated = (tx.raw_payload or {}).get("_generated") or {}
    return {
        "transaction": tx,
        "txn_type": generated.get("txn_type") or "—",
        "raw_json": json.dumps(tx.raw_payload, indent=2, default=str),
    }


def ingest_result_rows(ingest_file: IngestFile, limit: int = RESULT_ROW_LIMIT) -> dict:
    qs = transactions_for_ingest_file(ingest_file)
    total = qs.count()
    rows = [_display_row(tx) for tx in qs[:limit]]
    return {
        "rows": rows,
        "total_count": total,
        "truncated": total > limit,
        "limit": limit,
    }
