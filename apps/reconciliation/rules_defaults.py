"""Default rules seeded when a reconciliation project is created."""

from __future__ import annotations

from apps.reconciliation.recon_models import MatchRule, ReconProject

EXACT_REF_AMOUNT_DATE = {
    "min_confidence": 1.0,
    "where": [
        {"left": "source.external_ref", "op": "case_insensitive", "right": "target.external_ref"},
        {"left": "source.currency", "op": "exact", "right": "target.currency"},
        {"left": "source.amount", "op": "numeric_tolerance", "right": "target.amount", "epsilon": "0.01"},
        {"left": "source.timestamp", "op": "date_tolerance", "right": "target.timestamp", "days": 0},
    ],
}


def seed_default_rules(project: ReconProject) -> MatchRule:
    """Phase 5A behaviour as the first editable rule."""
    return MatchRule.objects.create(
        project=project,
        name="Ref + amount + date",
        priority=10,
        cardinality=MatchRule.Cardinality.ONE_TO_ONE,
        logic_mode=MatchRule.LogicMode.SIMPLE,
        definition=EXACT_REF_AMOUNT_DATE,
    )
