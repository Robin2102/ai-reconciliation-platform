"""Load Transaction rows for a reconciliation leg."""

from __future__ import annotations

from apps.ingestion.ingest_results import transactions_for_ingest_file
from apps.ingestion.models import IngestFile
from apps.reconciliation.models import Transaction
from apps.reconciliation.recon_models import ReconLeg


def transactions_for_leg(leg: ReconLeg):
    """All canonical transactions belonging to this leg's ingest upload."""
    return transactions_for_ingest_file(leg.ingest_file)


def leg_row_count(ingest_file: IngestFile) -> int:
    return transactions_for_ingest_file(ingest_file).count()
