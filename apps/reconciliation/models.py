from decimal import Decimal
from typing import List
from django.db import models, transaction
from apps.adaptors.base import CanonicalRecord


class Transaction(models.Model):
    """
    Canonical Transaction model storing normalized records ready for reconciliation.
    Maintains cr_amount/dr_amount alongside signed net amount for complete auditability.
    """
    source_id = models.CharField(max_length=100, db_index=True, help_text="Source identifier")
    external_ref = models.CharField(max_length=100, db_index=True, help_text="Upstream reference ID")
    cr_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), help_text="Credit amount (>= 0.00)")
    dr_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), help_text="Debit amount (>= 0.00)")
    amount = models.DecimalField(max_digits=18, decimal_places=2, help_text="Signed net amount (credit positive, debit negative)")
    currency = models.CharField(max_length=10, default="INR")
    timestamp = models.DateTimeField(db_index=True)
    description = models.TextField(blank=True, null=True)
    raw_payload = models.JSONField(default=dict, help_text="Original raw record payload")
    ingest_file = models.ForeignKey(
        "ingestion.IngestFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["source_id", "external_ref"]),
            models.Index(fields=["timestamp", "amount"]),
        ]

    def __str__(self):
        return f"Transaction({self.source_id}:{self.external_ref} | Amount: {self.amount} {self.currency})"


def save_canonical_records(
    records: List[CanonicalRecord],
    batch_size: int = 1000,
    ingest_file=None,
) -> List[Transaction]:
    """
    Atomically bulk save a list of CanonicalRecord Pydantic objects into Django Transaction database instances.
    """
    tx_instances = [
        Transaction(
            source_id=rec.source_id,
            external_ref=rec.external_ref,
            cr_amount=rec.cr_amount,
            dr_amount=rec.dr_amount,
            amount=rec.amount,
            currency=rec.currency,
            timestamp=rec.timestamp,
            description=rec.description,
            raw_payload=rec.raw_payload,
            ingest_file=ingest_file,
        )
        for rec in records
    ]

    with transaction.atomic():
        created = Transaction.objects.bulk_create(tx_instances, batch_size=batch_size)
    return created


# Reconciliation project models (Phase 5A) — imported for Django migrations.
from apps.reconciliation.recon_models import (  # noqa: E402,F401
    MatchResult,
    MatchRule,
    ReconLeg,
    ReconProject,
    ReconRun,
)

