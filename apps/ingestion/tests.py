from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ingestion.models import RawRecord
from apps.reconciliation.models import Transaction


CSV_BODY = (
    "txn_id,date,credit,debit,description,currency\n"
    "TXN-101,2026-09-12,1500.50,0.00,Salary,INR\n"
    "TXN-102,2026-09-12,0.00,200.00,Vendor,INR\n"
)


class IngestUploadApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_post_csv_creates_raw_and_transaction_rows(self):
        upload = SimpleUploadedFile("bank_sep.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "csv", "source_id": "hdfc-sep"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["raw_count"], 2)
        self.assertEqual(response.data["transaction_count"], 2)
        self.assertEqual(response.data["source_id"], "hdfc-sep")
        self.assertEqual(RawRecord.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertTrue(RawRecord.objects.filter(status="NORMALIZED").exists())
        salary = Transaction.objects.get(external_ref="TXN-101")
        self.assertEqual(str(salary.amount), "1500.50")

    def test_source_id_defaults_to_filename_stem(self):
        upload = SimpleUploadedFile("acme_ledger.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "csv"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["source_id"], "acme_ledger")

    def test_unknown_adapter_returns_400(self):
        upload = SimpleUploadedFile("data.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
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


class IngestUploadAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.user)
        self.upload_url = reverse("admin:ingestion_rawrecord_upload")

    def test_changelist_has_upload_link(self):
        response = self.client.get(reverse("admin:ingestion_rawrecord_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.upload_url)

    def test_upload_form_creates_rows(self):
        upload = SimpleUploadedFile("bank_sep.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "csv", "source_id": "hdfc-sep"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RawRecord.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_unknown_adapter_stays_on_form(self):
        upload = SimpleUploadedFile("data.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "sap", "source_id": "bad"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sap")
        self.assertEqual(RawRecord.objects.count(), 0)
