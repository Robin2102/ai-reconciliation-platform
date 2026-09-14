"""
Rule-based reconciliation (Phase 5B).

1. Load enabled rules by priority.
2. For each rule, greedily pair unmatched source/target rows (1:1).
3. Persist MatchResult + mark reconciled.
4. Create ExceptionRecord for remaining unmatched rows.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.exceptions.models import ExceptionRecord
from apps.reconciliation.engine.conditions import evaluate_where_clause
from apps.reconciliation.generated_fields import mark_reconciled_system
from apps.reconciliation.leg_data import transactions_for_leg
from apps.reconciliation.models import Transaction
from apps.reconciliation.recon_models import MatchResult, MatchRule, ReconRun


def _pair_score(rule: MatchRule, source: Transaction, target: Transaction) -> tuple[float, list[dict]]:
    definition = rule.definition or {}
    min_conf = float(definition.get("min_confidence", 1.0))
    if rule.logic_mode == MatchRule.LogicMode.IF_ELSE:
        if_part = definition.get("if") or {}
        score_if, det_if = evaluate_where_clause(if_part.get("where") or [], source, target)
        if score_if >= min_conf:
            return score_if, det_if
        else_part = definition.get("else") or {}
        score_else, det_else = evaluate_where_clause(else_part.get("where") or [], source, target)
        if score_else >= min_conf:
            return score_else, det_else
        return 0.0, det_else
    score, details = evaluate_where_clause(definition.get("where") or [], source, target)
    if score < min_conf:
        return 0.0, details
    return score, details


def run_reconciliation(run: ReconRun) -> dict[str, Any]:
    project = run.project
    source_leg = project.source_leg()
    target_leg = project.target_leg()
    if source_leg is None or target_leg is None:
        raise ValueError("Project needs both a source leg and a target leg.")

    source_list = list(transactions_for_leg(source_leg))
    target_list = list(transactions_for_leg(target_leg))
    rules = list(project.rules.filter(enabled=True).order_by("priority", "id"))
    if not rules:
        raise ValueError("Add at least one enabled match rule before running.")

    unmatched_source: dict[int, Transaction] = {tx.pk: tx for tx in source_list}
    unmatched_target: dict[int, Transaction] = {tx.pk: tx for tx in target_list}
    pairs: list[tuple[Transaction, Transaction, MatchRule, float, list]] = []

    for rule in rules:
        if rule.cardinality != MatchRule.Cardinality.ONE_TO_ONE:
            continue
        used_targets: set[int] = set()
        for source_id, source_tx in list(unmatched_source.items()):
            best_target = None
            best_score = 0.0
            best_details: list = []
            for target_id, target_tx in unmatched_target.items():
                if target_id in used_targets:
                    continue
                score, details = _pair_score(rule, source_tx, target_tx)
                if score > best_score:
                    best_score = score
                    best_target = target_tx
                    best_details = details
            if best_target is None or best_score <= 0:
                continue
            pairs.append((source_tx, best_target, rule, best_score, best_details))
            used_targets.add(best_target.pk)
            unmatched_source.pop(source_id, None)
            unmatched_target.pop(best_target.pk, None)

    reconciled_at = timezone.now()
    match_rows: list[MatchResult] = []
    exception_rows: list[ExceptionRecord] = []
    txs_to_update: list[Transaction] = []

    for source_tx, target_tx, rule, score, details in pairs:
        match_rows.append(
            MatchResult(
                run=run,
                source_transaction=source_tx,
                target_transaction=target_tx,
                confidence=Decimal(str(round(score, 4))),
                rule_name=rule.name,
                explanation={"conditions": details, "rule_id": rule.pk},
            )
        )
        for tx in (source_tx, target_tx):
            payload = dict(tx.raw_payload or {})
            mark_reconciled_system(payload, at=reconciled_at)
            tx.raw_payload = payload
            txs_to_update.append(tx)

    for tx in unmatched_source.values():
        exception_rows.append(
            ExceptionRecord(
                project=project,
                run=run,
                transaction=tx,
                side=ExceptionRecord.Side.SOURCE,
                reason="no_matching_target",
            )
        )
    for tx in unmatched_target.values():
        exception_rows.append(
            ExceptionRecord(
                project=project,
                run=run,
                transaction=tx,
                side=ExceptionRecord.Side.TARGET,
                reason="no_matching_source",
            )
        )

    with transaction.atomic():
        MatchResult.objects.bulk_create(match_rows, batch_size=500)
        ExceptionRecord.objects.bulk_create(exception_rows, batch_size=500)
        if txs_to_update:
            Transaction.objects.bulk_update(txs_to_update, ["raw_payload"], batch_size=500)

    return {
        "matched_pairs": len(pairs),
        "unmatched_source": len(unmatched_source),
        "unmatched_target": len(unmatched_target),
        "exceptions_created": len(exception_rows),
        "source_rows": len(source_list),
        "target_rows": len(target_list),
        "rules_applied": [r.name for r in rules],
    }
