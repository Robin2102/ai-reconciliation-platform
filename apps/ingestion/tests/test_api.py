from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.ingestion.models import RawRecord
from apps.ingestion.tests.fixtures import BANK_SEP_CSV
from apps.reconciliation.models import Transaction


class IngestUploadApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_post_csv_creates_raw_and_transaction_rows(self):
        upload = SimpleUploadedFile("bank_sep.csv", BANK_SEP_CSV.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "csv", "source_id": "hdfc-sep"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.data["status"], "queued")
        self.assertTrue(response.data["task_id"])
        self.assertEqual(response.data["source_id"], "hdfc-sep")
        self.assertEqual(RawRecord.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertTrue(RawRecord.objects.filter(status="NORMALIZED").exists())
        salary = Transaction.objects.get(external_ref="TXN-101")
        self.assertEqual(str(salary.amount), "1500.50")

    def test_source_id_defaults_to_filename_stem(self):
        upload = SimpleUploadedFile("acme_ledger.csv", BANK_SEP_CSV.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "csv"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.data["source_id"], "acme_ledger")

    def test_unknown_adapter_returns_400(self):
        upload = SimpleUploadedFile("data.csv", BANK_SEP_CSV.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "sap"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("sap", str(response.data["detail"]))
        self.assertEqual(RawRecord.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_missing_file_returns_400(self):
        response = self.client.post("/api/ingest/", {"source_type": "csv"}, format="multipart")
        self.assertEqual(response.status_code, 400)
