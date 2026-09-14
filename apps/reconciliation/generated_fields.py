"""Update `_generated` reconciliation metadata on Transaction payloads (Phase 5–6 hooks)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from django.contrib.auth.models import AbstractUser
from django.utils import timezone as dj_tz

from apps.reconciliation.models import Transaction

GENERATED_KEY = "_generated"
RECONCILED_BY_SYSTEM = "System"


def _ensure_generated(payload: dict[str, Any]) -> dict[str, Any]:
    block = payload.get(GENERATED_KEY)
    if not isinstance(block, dict):
        block = {}
        payload[GENERATED_KEY] = block
    return block


def mark_reconciled_system(payload: dict[str, Any], at: datetime | None = None) -> dict[str, Any]:
    when = at or dj_tz.now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    block = _ensure_generated(payload)
    block["reconciled_date"] = when.astimezone(timezone.utc).isoformat()
    block["reconciled_by"] = RECONCILED_BY_SYSTEM
    return payload


def mark_reconciled_manual(payload: dict[str, Any], user: AbstractUser, at: datetime | None = None) -> dict[str, Any]:
    when = at or dj_tz.now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    block = _ensure_generated(payload)
    block["reconciled_date"] = when.astimezone(timezone.utc).isoformat()
    block["reconciled_by"] = user.get_username()
    return payload


def apply_generated_to_transaction(tx: Transaction, payload: dict[str, Any]) -> None:
    tx.raw_payload = payload
    tx.save(update_fields=["raw_payload"])
