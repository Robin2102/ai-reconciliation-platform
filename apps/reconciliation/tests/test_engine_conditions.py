from django.test import TestCase

from apps.reconciliation.engine.conditions import evaluate_condition
from apps.reconciliation.engine.rule_runner import run_reconciliation
from apps.reconciliation.models import Transaction
from apps.reconciliation.project_service import create_recon_project
from apps.reconciliation.recon_models import MatchRule, ReconRun
from apps.reconciliation.rule_templates import RULE_TEMPLATES
from apps.reconciliation.tests.helpers import stage_done_ingest


class ConditionEvaluatorTests(TestCase):
    def test_numeric_tolerance(self):
        bank = Transaction(
            external_ref="A", amount="100.00", currency="INR", timestamp="2026-09-12T00:00:00Z"
        )
        gl = Transaction(
            external_ref="A", amount="100.005", currency="INR", timestamp="2026-09-12T00:00:00Z"
        )
        cond = {
            "left": "source.amount",
            "op": "numeric_tolerance",
            "right": "target.amount",
            "epsilon": "0.01",
        }
        self.assertEqual(evaluate_condition(cond, bank, gl), 1.0)


class FuzzyRuleRunTests(TestCase):
    def test_fuzzy_ref_template_matches_similar_refs(self):
        bank_csv = "txn_id,date,credit,debit,currency\nTXN1,2026-09-12,10,0,INR\n"
        gl_csv = "ref,date,credit,debit,currency\nTXN-1,2026-09-12,10,0,INR\n"
        bank_f = stage_done_ingest("b.csv", "b-fuzzy", bank_csv)
        gl_f = stage_done_ingest("g.csv", "g-fuzzy", gl_csv)

        project = create_recon_project("fuzzy", "", bank_f.pk, gl_f.pk)
        project.rules.all().delete()
        tpl = RULE_TEMPLATES["fuzzy_ref_exact_amount"]
        MatchRule.objects.create(
            project=project,
            name="fuzzy",
            priority=5,
            logic_mode=tpl["logic_mode"],
            definition=tpl["definition"],
        )
        run = ReconRun.objects.create(project=project)
        stats = run_reconciliation(run)
        self.assertEqual(stats["matched_pairs"], 1)
