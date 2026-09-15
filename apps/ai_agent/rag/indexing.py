"""Build knowledge chunks from domain objects."""

from __future__ import annotations

from apps.ai_agent.models import KnowledgeChunk
from apps.ai_agent.rag.embeddings import embed_text
from apps.exceptions.models import ExceptionRecord


def exception_query_text(record: ExceptionRecord) -> str:
    """Short query for retrieving similar *past* cases for an open exception."""
    tx = record.transaction
    parts = [
        f"reason: {record.reason}",
        f"reference: {tx.external_ref}",
        f"amount: {tx.amount} {tx.currency}",
        f"source_id: {tx.source_id}",
    ]
    if tx.description:
        parts.append(f"description: {tx.description}")
    return "\n".join(parts)


def exception_document_text(record: ExceptionRecord) -> str:
    """Plain-text case summary for embedding (no encrypted PII blobs)."""
    tx = record.transaction
    lines = [
        f"reason: {record.reason}",
        f"side: {record.side}",
        f"status: {record.status}",
        f"reference: {tx.external_ref}",
        f"amount: {tx.amount} {tx.currency}",
        f"transaction_date: {tx.timestamp}",
        f"source_id: {tx.source_id}",
    ]
    if tx.description:
        lines.append(f"description: {tx.description}")
    if record.resolution_kind:
        lines.append(f"resolution: {record.resolution_kind}")
    if record.resolution_note:
        lines.append(f"resolution_note: {record.resolution_note}")
    if record.paired_transaction_id:
        pt = record.paired_transaction
        if pt:
            lines.append(f"paired_reference: {pt.external_ref}")
    return "\n".join(lines)


def index_exception_record(record: ExceptionRecord) -> KnowledgeChunk | None:
    """Upsert a chunk for a closed exception (resolved or rejected with context)."""
    if record.status not in (
        ExceptionRecord.Status.RESOLVED,
        ExceptionRecord.Status.REJECTED,
    ):
        return None
    text = exception_document_text(record)
    if not text.strip():
        return None
    vector = embed_text(text)
    metadata = {
        "exception_id": record.pk,
        "project_id": record.project_id,
        "resolution_kind": record.resolution_kind,
        "external_ref": record.transaction.external_ref,
        "source_id": record.transaction.source_id,
    }
    chunk, _ = KnowledgeChunk.objects.update_or_create(
        exception=record,
        defaults={
            "kind": KnowledgeChunk.Kind.RESOLVED_EXCEPTION,
            "project_id": record.project_id,
            "text": text,
            "embedding": vector,
            "metadata": metadata,
        },
    )
    return chunk


def index_all_resolved_exceptions() -> int:
    count = 0
    qs = ExceptionRecord.objects.filter(
        status__in=[ExceptionRecord.Status.RESOLVED, ExceptionRecord.Status.REJECTED]
    ).select_related("transaction", "paired_transaction")
    for record in qs.iterator():
        if index_exception_record(record):
            count += 1
    return count
