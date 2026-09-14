"""
Evaluate one condition between a source and target Transaction.

Each condition returns a score 0.0–1.0. Simple rules require all conditions
to score 1.0 (or average >= min_confidence).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from apps.reconciliation.engine.fields import field_value, parse_field_path
from apps.reconciliation.models import Transaction


def _as_decimal(val) -> Decimal:
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _as_date(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def evaluate_condition(condition: dict, source: Transaction, target: Transaction) -> float:
    op = (condition.get("op") or "exact").strip().lower()
    left_path = condition.get("left") or ""
    right_path = condition.get("right") or ""

    left_side, left_field = parse_field_path(left_path)
    right_side, right_field = parse_field_path(right_path)
    left_val = field_value(source if left_side == "source" else target, left_field)
    right_val = field_value(source if right_side == "source" else target, right_field)

    if op == "exact":
        return 1.0 if str(left_val or "") == str(right_val or "") else 0.0

    if op == "case_insensitive":
        return 1.0 if str(left_val or "").lower() == str(right_val or "").lower() else 0.0

    if op == "numeric_tolerance":
        epsilon = _as_decimal(condition.get("epsilon", "0.01"))
        return 1.0 if abs(_as_decimal(left_val) - _as_decimal(right_val)) <= epsilon else 0.0

    if op == "date_tolerance":
        days = int(condition.get("days", 0))
        left_d = _as_date(left_val)
        right_d = _as_date(right_val)
        if left_d is None or right_d is None:
            return 0.0
        return 1.0 if abs((left_d - right_d).days) <= days else 0.0

    if op == "fuzzy":
        threshold = float(condition.get("threshold", 0.85))
        ratio = SequenceMatcher(None, str(left_val or ""), str(right_val or "")).ratio()
        return ratio if ratio >= threshold else 0.0

    raise ValueError(f"Unknown condition op: {op}")


def evaluate_where_clause(where: list[dict], source: Transaction, target: Transaction) -> tuple[float, list[dict]]:
    """Average condition score; details per condition for explainability."""
    if not where:
        return 0.0, []
    scores: list[float] = []
    details: list[dict] = []
    for cond in where:
        score = evaluate_condition(cond, source, target)
        scores.append(score)
        details.append({**cond, "score": score})
    avg = sum(scores) / len(scores)
    return avg, details
