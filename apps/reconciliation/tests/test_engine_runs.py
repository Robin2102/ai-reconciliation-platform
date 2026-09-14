from django.test import TestCase

from apps.ingestion.models import IngestFile
from apps.reconciliation.engine.rule_runner import run_reconciliation
from apps.reconciliation.models import Transaction
from apps.reconciliation.project_service import create_recon_project
from apps.reconciliation.recon_models import ReconRun
from apps.reconciliation.tests.helpers import stage_done_ingest

BANK_CSV = (
    "txn_id,date,credit,debit,description,currency\n"
    "TXN-1,2026-09-12,100.00,0.00,Pay A,INR\n"
    "TXN-2,2026-09-12,0.00,50.00,Pay B,INR\n"
    "TXN-ONLY-SRC,2026-09-12,10.00,0.00,Orphan,INR\n"
)

GL_CSV = (
    "ref,date,credit,debit,description,currency\n"
    "TXN-1,2026-09-12,100.00,0.00,Pay A,INR\n"
    "TXN-2,2026-09-12,0.00,50.00,Pay B,INR\n"
    "TXN-ONLY-TGT,2026-09-12,0.00,25.00,Extra,INR\n"
)


class ReconRunTests(TestCase):
    def test_match_pairs_unmatched_and_exceptions(self):
        bank = stage_done_ingest("bank.csv", "bank-sep", BANK_CSV)
        gl = stage_done_ingest("gl.csv", "gl-sep", GL_CSV)

        project = create_recon_project("Sep recon", "", bank.pk, gl.pk)
        run = ReconRun.objects.create(project=project)
        stats = run_reconciliation(run)

        self.assertEqual(stats["matched_pairs"], 2)
        self.assertEqual(stats["unmatched_source"], 1)
        self.assertEqual(stats["unmatched_target"], 1)
        self.assertEqual(stats["exceptions_created"], 2)
        self.assertEqual(run.results.count(), 2)

        matched_tx = Transaction.objects.get(external_ref="TXN-1", source_id="bank-sep")
        self.assertEqual(matched_tx.raw_payload["_generated"]["reconciled_by"], "System")

    def test_create_project_rejects_non_done_ingest(self):
        staged = IngestFile.objects.create(
            path="/x",
            original_name="x.csv",
            source_type="csv",
            source_id="x",
            status=IngestFile.Status.STAGED,
        )
        done = stage_done_ingest("ok.csv", "ok", BANK_CSV)
        with self.assertRaises(ValueError):
            create_recon_project("bad", "", staged.pk, done.pk)
