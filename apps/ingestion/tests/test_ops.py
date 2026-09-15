from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.ingestion.models import IngestionJob, MappingTemplate
from apps.ingestion.tests.fixtures import BANK_SEP_CSV
from apps.reconciliation.models import Transaction


def _mapping_form_data(template: MappingTemplate) -> dict:
    data = {
        "action": "save",
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
    return data


class IngestOpsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.user)

    def test_anonymous_redirects_to_ops_login(self):
        self.client.logout()
        response = self.client.get(reverse("ops-jobs"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ops/login/", response["Location"])

    def test_ops_root_redirects_to_connectors(self):
        response = self.client.get("/ops/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ops/connectors/", response["Location"])

    def test_job_upload_mapping_and_run_creates_rows(self):
        upload = SimpleUploadedFile("bank_sep.csv", BANK_SEP_CSV.encode("utf-8"), content_type="text/csv")
        create_resp = self.client.post(
            reverse("ops-job-create"),
            {
                "action": "create_job",
                "name": "Sep bank",
                "source_id": "hdfc-sep",
                "default_source_type": "csv",
                "input_mode": "upload",
                "files": upload,
            },
        )
        self.assertEqual(create_resp.status_code, 302, create_resp.content)
        self.assertIn("/mapping/", create_resp["Location"])
        job = IngestionJob.objects.get(source_id="hdfc-sep")
        mapping_url = reverse("ops-job-mapping", kwargs={"job_id": job.pk})
        get_resp = self.client.get(mapping_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "txn_id")
        template = MappingTemplate.objects.get(source_id="hdfc-sep")
        save_resp = self.client.post(mapping_url, _mapping_form_data(template))
        self.assertEqual(save_resp.status_code, 302, save_resp.content)
        job.refresh_from_db()
        self.assertEqual(job.status, IngestionJob.Status.READY)
        run_resp = self.client.post(reverse("ops-job-run", kwargs={"job_id": job.pk}))
        self.assertEqual(run_resp.status_code, 302, run_resp.content)
        self.assertEqual(Transaction.objects.filter(source_id="hdfc-sep").count(), 2)
        job.refresh_from_db()
        run = job.runs.first()
        self.assertIsNotNone(run)
        results_url = reverse("ops-ingest-results", kwargs={"file_id": run.primary_ingest_file_id})
        results = self.client.get(results_url)
        self.assertEqual(results.status_code, 200)
        self.assertContains(results, "TXN-101")
        self.assertContains(results, "bank_sep.csv")

    def test_header_only_upload_rejected_on_job_create(self):
        body = "txn_id,date,credit,debit\n"
        upload = SimpleUploadedFile("headers_only.csv", body.encode("utf-8"), content_type="text/csv")
        response = self.client.post(
            reverse("ops-job-create"),
            {
                "action": "create_job",
                "name": "Empty",
                "source_id": "empty",
                "default_source_type": "csv",
                "input_mode": "upload",
                "files": upload,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No data rows")
        self.assertEqual(IngestionJob.objects.filter(source_id="empty").count(), 0)
