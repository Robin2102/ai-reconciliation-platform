"""Exception lifecycle: investigate, resolve, reject (Phase 6)."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

from apps.exceptions.models import ExceptionRecord
from apps.reconciliation.generated_fields import mark_reconciled_manual
from apps.reconciliation.leg_data import transactions_for_leg
from apps.reconciliation.models import Transaction
from apps.reconciliation.recon_models import MatchResult, ReconProject


class ExceptionWorkflowError(ValueError):
    pass


def _opposite_leg_tx_ids(project: ReconProject, record: ExceptionRecord) -> set[int]:
    if record.side == ExceptionRecord.Side.SOURCE:
        leg = project.target_leg()
    else:
        leg = project.source_leg()
    if leg is None:
        return set()
    return set(transactions_for_leg(leg).values_list("pk", flat=True))


def start_investigating(record: ExceptionRecord, user: AbstractUser) -> ExceptionRecord:
    if record.status != ExceptionRecord.Status.OPEN:
        raise ExceptionWorkflowError("Only open exceptions can be moved to investigating.")
    record.status = ExceptionRecord.Status.INVESTIGATING
    record.save(update_fields=["status", "updated_at"])
    return record


def reject_exception(record: ExceptionRecord, user: AbstractUser, note: str = "") -> ExceptionRecord:
    if record.status in (ExceptionRecord.Status.RESOLVED, ExceptionRecord.Status.REJECTED):
        raise ExceptionWorkflowError("This exception is already closed.")
    record.status = ExceptionRecord.Status.REJECTED
    record.resolution_kind = ExceptionRecord.ResolutionKind.REJECTED
    record.resolution_note = (note or "").strip()
    record.resolved_by = user
    record.resolved_at = timezone.now()
    record.save(
        update_fields=[
            "status",
            "resolution_kind",
            "resolution_note",
            "resolved_by",
            "resolved_at",
            "updated_at",
        ]
    )
    _index_for_rag(record)
    return record


def _index_for_rag(record: ExceptionRecord) -> None:
    try:
        from apps.ai_agent.rag.indexing import index_exception_record

        index_exception_record(record)
    except Exception:
        pass


def resolve_write_off(record: ExceptionRecord, user: AbstractUser, note: str = "") -> ExceptionRecord:
    if record.status in (ExceptionRecord.Status.RESOLVED, ExceptionRecord.Status.REJECTED):
        raise ExceptionWorkflowError("This exception is already closed.")
    if not (note or "").strip():
        raise ExceptionWorkflowError("Write-off requires a resolution note.")
    tx = record.transaction
    payload = dict(tx.raw_payload or {})
    mark_reconciled_manual(payload, user)
    tx.raw_payload = payload
    tx.save(update_fields=["raw_payload"])

    record.status = ExceptionRecord.Status.RESOLVED
    record.resolution_kind = ExceptionRecord.ResolutionKind.WRITE_OFF
    record.resolution_note = note.strip()
    record.resolved_by = user
    record.resolved_at = timezone.now()
    record.save(
        update_fields=[
            "status",
            "resolution_kind",
            "resolution_note",
            "resolved_by",
            "resolved_at",
            "updated_at",
        ]
    )
    _index_for_rag(record)
    return record


@transaction.atomic
def resolve_manual_match(
    record: ExceptionRecord,
    user: AbstractUser,
    counterparty: Transaction,
    note: str = "",
) -> ExceptionRecord:
    if record.status in (ExceptionRecord.Status.RESOLVED, ExceptionRecord.Status.REJECTED):
        raise ExceptionWorkflowError("This exception is already closed.")

    project = record.project
    allowed = _opposite_leg_tx_ids(project, record)
    if counterparty.pk not in allowed:
        raise ExceptionWorkflowError("Counterparty must be a row on the opposite leg.")

    if record.side == ExceptionRecord.Side.SOURCE:
        source_tx, target_tx = record.transaction, counterparty
    else:
        source_tx, target_tx = counterparty, record.transaction

    MatchResult.objects.create(
        run=record.run,
        source_transaction=source_tx,
        target_transaction=target_tx,
        confidence=Decimal("1"),
        rule_name="manual_ops",
        explanation={
            "resolution": "manual_match",
            "exception_id": record.pk,
            "note": (note or "").strip(),
            "resolved_by": user.get_username(),
        },
    )
    for tx in (source_tx, target_tx):
        payload = dict(tx.raw_payload or {})
        mark_reconciled_manual(payload, user)
        tx.raw_payload = payload
        tx.save(update_fields=["raw_payload"])

    _mark_resolved(record, user, ExceptionRecord.ResolutionKind.MANUAL_MATCH, note, counterparty)

    sibling = (
        ExceptionRecord.objects.filter(
            project=project,
            transaction=counterparty,
            status__in=[ExceptionRecord.Status.OPEN, ExceptionRecord.Status.INVESTIGATING],
        )
        .exclude(pk=record.pk)
        .first()
    )
    if sibling:
        _mark_resolved(
            sibling,
            user,
            ExceptionRecord.ResolutionKind.MANUAL_MATCH,
            note or "Closed via paired manual match.",
            record.transaction,
        )
    return record


def _mark_resolved(
    record: ExceptionRecord,
    user: AbstractUser,
    kind: str,
    note: str,
    paired: Transaction | None,
) -> None:
    record.status = ExceptionRecord.Status.RESOLVED
    record.resolution_kind = kind
    record.resolution_note = (note or "").strip()
    record.resolved_by = user
    record.resolved_at = timezone.now()
    record.paired_transaction = paired
    record.save(
        update_fields=[
            "status",
            "resolution_kind",
            "resolution_note",
            "resolved_by",
            "resolved_at",
            "paired_transaction",
            "updated_at",
        ]
    )
    _index_for_rag(record)
