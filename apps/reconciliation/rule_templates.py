"""Preset rule definitions for the ops rule builder."""

from __future__ import annotations

from apps.reconciliation.rules_defaults import EXACT_REF_AMOUNT_DATE

RULE_TEMPLATES = {
    "exact_ref_amount_date": {
        "label": "Reference + amount (±0.01) + same day",
        "logic_mode": "simple",
        "definition": EXACT_REF_AMOUNT_DATE,
    },
    "fuzzy_ref_exact_amount": {
        "label": "Fuzzy reference (85%) + exact amount + same day",
        "logic_mode": "simple",
        "definition": {
            "min_confidence": 0.85,
            "where": [
                {
                    "left": "source.external_ref",
                    "op": "fuzzy",
                    "right": "target.external_ref",
                    "threshold": 0.85,
                },
                {"left": "source.currency", "op": "exact", "right": "target.currency"},
                {"left": "source.amount", "op": "numeric_tolerance", "right": "target.amount", "epsilon": "0.01"},
                {"left": "source.timestamp", "op": "date_tolerance", "right": "target.timestamp", "days": 0},
            ],
        },
    },
    "if_else_amount_fallback": {
        "label": "If/else: strict ref OR same amount+date",
        "logic_mode": "if_else",
        "definition": {
            "min_confidence": 1.0,
            "if": {
                "where": [
                    {
                        "left": "source.external_ref",
                        "op": "case_insensitive",
                        "right": "target.external_ref",
                    },
                    {"left": "source.currency", "op": "exact", "right": "target.currency"},
                ],
            },
            "else": {
                "where": [
                    {"left": "source.amount", "op": "exact", "right": "target.amount"},
                    {"left": "source.timestamp", "op": "date_tolerance", "right": "target.timestamp", "days": 1},
                ],
            },
        },
    },
}
