from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.exceptions.models import ExceptionRecord
from apps.exceptions.services import (
    ExceptionWorkflowError,
    reject_exception,
    resolve_manual_match,
    resolve_write_off,
    start_investigating,
)
from apps.reconciliation.engine.rule_runner import run_reconciliation
from apps.reconciliation.project_service import create_recon_project
from apps.reconciliation.recon_models import ReconRun
from apps.reconciliation.tests.helpers import stage_done_ingest

BANK = (
    "txn_id,date,credit,debit,currency\n"
    "ONLY-SRC,2026-09-12,10,0,INR\n"
)
GL = (
    "ref,date,credit,debit,currency\n"
    "ONLY-TGT,2026-09-12,0,5,INR\n"
)


class ExceptionWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ops", password="pass")
        bank = stage_done_ingest("b.csv", "ex-bank", BANK)
        gl = stage_done_ingest("g.csv", "ex-gl", GL)
        self.project = create_recon_project("ex", "", bank.pk, gl.pk)
        run = ReconRun.objects.create(project=self.project)
        run_reconciliation(run)
        self.run = run
        self.src_ex = ExceptionRecord.objects.get(transaction__external_ref="ONLY-SRC")
        self.tgt_ex = ExceptionRecord.objects.get(transaction__external_ref="ONLY-TGT")

    def test_investigate_and_write_off(self):
        start_investigating(self.src_ex, self.user)
        self.src_ex.refresh_from_db()
        self.assertEqual(self.src_ex.status, ExceptionRecord.Status.INVESTIGATING)
        resolve_write_off(self.src_ex, self.user, "Timing difference accepted")
        self.src_ex.refresh_from_db()
        self.assertEqual(self.src_ex.status, ExceptionRecord.Status.RESOLVED)
        self.assertEqual(self.src_ex.resolution_kind, ExceptionRecord.ResolutionKind.WRITE_OFF)
        tx = self.src_ex.transaction
        tx.refresh_from_db()
        self.assertEqual(tx.raw_payload["_generated"]["reconciled_by"], "ops")

    def test_manual_match_closes_both_exceptions(self):
        resolve_manual_match(
            self.src_ex,
            self.user,
            self.tgt_ex.transaction,
            "Matched in ops",
        )
        self.src_ex.refresh_from_db()
        self.tgt_ex.refresh_from_db()
        self.assertEqual(self.src_ex.status, ExceptionRecord.Status.RESOLVED)
        self.assertEqual(self.tgt_ex.status, ExceptionRecord.Status.RESOLVED)
        self.assertEqual(self.run.results.filter(rule_name="manual_ops").count(), 1)

    def test_reject_does_not_mark_transaction(self):
        tx = self.tgt_ex.transaction
        payload_before = dict(tx.raw_payload or {})
        reject_exception(self.tgt_ex, self.user, "Not our account")
        tx.refresh_from_db()
        self.assertEqual(self.tgt_ex.status, ExceptionRecord.Status.REJECTED)
        self.assertEqual(tx.raw_payload, payload_before)

    def test_write_off_requires_note(self):
        with self.assertRaises(ExceptionWorkflowError):
            resolve_write_off(self.src_ex, self.user, "")


class ExceptionOpsViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(self.user)
        bank = stage_done_ingest("b.csv", "view-bank", BANK)
        gl = stage_done_ingest("g.csv", "view-gl", GL)
        self.project = create_recon_project("view", "", bank.pk, gl.pk)
        run = ReconRun.objects.create(project=self.project)
        run_reconciliation(run)
        self.exception = ExceptionRecord.objects.filter(status=ExceptionRecord.Status.OPEN).first()

    def test_exception_list_filter(self):
        url = reverse("ops-recon-exceptions", kwargs={"project_id": self.project.pk})
        response = self.client.get(url, {"status": "open"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ONLY-SRC")

    def test_investigate_via_post(self):
        url = reverse(
            "ops-recon-exception-action",
            kwargs={"project_id": self.project.pk, "exception_id": self.exception.pk},
        )
        response = self.client.post(url, {"action": "investigate"})
        self.assertEqual(response.status_code, 302)
        self.exception.refresh_from_db()
        self.assertEqual(self.exception.status, ExceptionRecord.Status.INVESTIGATING)
