from unittest.mock import patch
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ingestion.models import IngestFile, RawRecord
from apps.ingestion.services import infer_source_type, ingest_source
from apps.reconciliation.models import Transaction


CSV_BODY = (
    "txn_id,date,credit,debit,description,currency\n"
    "TXN-101,2026-09-12,1500.50,0.00,Salary,INR\n"
    "TXN-102,2026-09-12,0.00,200.00,Vendor,INR\n"
)


class InferSourceTypeTests(TestCase):
    def test_txt_extension_defaults_to_txt_adapter(self):
        self.assertEqual(infer_source_type("ledger.txt", "csv"), "txt")

    def test_csv_extension_stays_csv(self):
        self.assertEqual(infer_source_type("ledger.csv", "csv"), "csv")

    def test_explicit_txt_respected(self):
        self.assertEqual(infer_source_type("data.csv", "txt"), "txt")


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
        upload = SimpleUploadedFile("acme_ledger.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            "/api/ingest/",
            {"file": upload, "source_type": "csv"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.content)
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


class IngestOpsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.user)
        self.upload_url = reverse("ops-ingest")

    def test_anonymous_redirects_to_ops_login(self):
        self.client.logout()
        response = self.client.get(self.upload_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ops/login/", response["Location"])

    def test_admin_changelist_has_no_upload_workflow(self):
        response = self.client.get(reverse("admin:ingestion_rawrecord_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/ops/")
        self.assertNotContains(response, "Upload CSV")

    def test_upload_stages_file_without_ingest(self):
        upload = SimpleUploadedFile("bank_sep.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "csv", "source_id": "hdfc-sep"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ops/mapping/", response["Location"])
        self.assertEqual(RawRecord.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)
        staged = IngestFile.objects.get(source_id="hdfc-sep")
        self.assertEqual(staged.status, IngestFile.Status.STAGED)

    def test_run_ingest_from_mapping_creates_rows(self):
        upload = SimpleUploadedFile("bank_sep.csv", CSV_BODY.encode("utf-8"), content_type="text/csv")
        self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "csv", "source_id": "hdfc-sep"},
        )
        ingest_file = IngestFile.objects.get(source_id="hdfc-sep")
        mapping_url = reverse("ops-mapping", kwargs={"file_id": ingest_file.pk})
        get_resp = self.client.get(mapping_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "txn_id")
        from apps.ingestion.models import MappingTemplate

        template = MappingTemplate.objects.get(source_id="hdfc-sep")
        data = {
            "action": "ingest",
            "template_name": template.name,
            "default_currency": "INR",
            "normalize_headers": "on",
        }
        for i, col in enumerate(template.columns.all()):
            data[f"col-{i}-detected_type"] = col.detected_type
            data[f"col-{i}-role"] = col.role
            data[f"col-{i}-mapped_name"] = col.mapped_name
            data[f"col-{i}-null_policy"] = col.null_policy
            data[f"col-{i}-date_format"] = col.date_format
            data[f"col-{i}-pii"] = col.pii
            if (col.extra or {}).get("trim", True):
                data[f"col-{i}-trim"] = "on"
        response = self.client.post(mapping_url, data)
        self.assertEqual(response.status_code, 302, response.content)
        self.assertEqual(RawRecord.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)

    def test_ingest_parse_error_is_shown_on_mapping_page(self):
        body = (
            "txn_id,date,credit,debit,description,currency\n"
            "TXN-101,261,1500.50,0.00,Salary,INR\n"
        )
        upload = SimpleUploadedFile("bad_dates.csv", body.encode("utf-8"), content_type="text/csv")
        self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "csv", "source_id": "bad-dates"},
        )
        ingest_file = IngestFile.objects.get(source_id="bad-dates")
        mapping_url = reverse("ops-mapping", kwargs={"file_id": ingest_file.pk})
        self.client.get(mapping_url)
        from apps.ingestion.models import MappingTemplate

        template = MappingTemplate.objects.get(source_id="bad-dates")
        data = {
            "action": "ingest",
            "template_name": template.name,
            "default_currency": "INR",
            "normalize_headers": "on",
        }
        for i, col in enumerate(template.columns.all()):
            data[f"col-{i}-detected_type"] = col.detected_type
            data[f"col-{i}-role"] = col.role
            data[f"col-{i}-mapped_name"] = col.mapped_name
            data[f"col-{i}-null_policy"] = col.null_policy
            data[f"col-{i}-date_format"] = col.date_format or "YYYY-MM-DD"
            data[f"col-{i}-pii"] = col.pii
            if (col.extra or {}).get("trim", True):
                data[f"col-{i}-trim"] = "on"
        response = self.client.post(mapping_url, data)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertContains(response, "Ingest failed")
        self.assertContains(response, "could not parse")
        self.assertContains(response, "261")
        ingest_file.refresh_from_db()
        self.assertEqual(ingest_file.status, IngestFile.Status.ERROR)
        self.assertIn("261", ingest_file.error_message)
        self.assertEqual(Transaction.objects.count(), 0)
        home = self.client.get(self.upload_url)
        self.assertContains(home, "261")

    def test_header_only_file_rejected_at_stage(self):
        body = "txn_id,date,credit,debit\n"
        upload = SimpleUploadedFile("headers_only.csv", body.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            self.upload_url,
            {"file": upload, "source_type": "csv", "source_id": "empty"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No data rows")
        self.assertEqual(IngestFile.objects.filter(source_id="empty").count(), 0)

    def test_upload_form_lists_registered_adapters(self):
        response = self.client.get(self.upload_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CSV — delimited")
        self.assertContains(response, "TXT — delimited")


class KafkaPublishTests(TestCase):
    @override_settings(KAFKA_ENABLED=True)
    @patch("apps.ingestion.services.publish_record_ingested")
    def test_ingest_source_publishes_after_commit(self, publish):
        ingest_source("csv", "hdfc-sep", io.BytesIO(CSV_BODY.encode("utf-8")))
        publish.assert_called_once()
        payload = publish.call_args[0][0]
        self.assertEqual(payload["source_id"], "hdfc-sep")
        self.assertEqual(payload["source_type"], "csv")
        self.assertEqual(payload["transaction_count"], 2)
        self.assertEqual(len(payload["transaction_ids"]), 2)
        self.assertEqual(Transaction.objects.count(), 2)
