"""Resolve `source.amount`-style paths on Transaction rows."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from apps.reconciliation.models import Transaction

ALLOWED_FIELDS = (
    "external_ref",
    "amount",
    "cr_amount",
    "dr_amount",
    "currency",
    "timestamp",
    "description",
)


def parse_field_path(path: str) -> tuple[str, str]:
    """`source.external_ref` -> ('source', 'external_ref')."""
    parts = (path or "").strip().split(".", 1)
    if len(parts) != 2 or parts[0] not in {"source", "target"}:
        raise ValueError(f"Invalid field path: {path}")
    side, field = parts[0], parts[1]
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Unsupported field {field!r} in path {path}")
    return side, field


def field_value(tx: Transaction, field: str):
    if field == "timestamp":
        return tx.timestamp
    if field in {"amount", "cr_amount", "dr_amount"}:
        return tx.__getattribute__(field)
    value = getattr(tx, field, None)
    return value
