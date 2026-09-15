import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.connectors.models import Connector
from apps.ingestion.merged_ingest import execute_merged_ingestion_run
from apps.ingestion.models import IngestionJob, IngestionJobInput, IngestionJobRun, MappingTemplate, ColumnMapping
from apps.ingestion.mapping import validate_template
from apps.reconciliation.models import Transaction


class MergedIngestionJobTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)
        (self.base / "a.csv").write_text(
            "txn_id,date,credit,debit,currency\nT1,2026-09-12,1,0,INR\n", encoding="utf-8"
        )
        (self.base / "b.csv").write_text(
            "txn_id,date,credit,debit,currency\nT2,2026-09-12,2,0,INR\n", encoding="utf-8"
        )
        self.allowlist = [str(self.base)]

    def _template(self, source_id: str) -> MappingTemplate:
        tpl = MappingTemplate.objects.create(name="t", source_id=source_id, default_currency="INR")
        ColumnMapping.objects.create(
            template=tpl, source_header="txn_id", role=ColumnMapping.Role.EXTERNAL_REF
        )
        ColumnMapping.objects.create(
            template=tpl,
            source_header="date",
            role=ColumnMapping.Role.TIMESTAMP,
            date_format="YYYY-MM-DD",
        )
        ColumnMapping.objects.create(template=tpl, source_header="credit", role=ColumnMapping.Role.CR_AMOUNT)
        ColumnMapping.objects.create(template=tpl, source_header="debit", role=ColumnMapping.Role.DR_AMOUNT)
        validate_template(tpl)
        return tpl

    def test_merged_job_sets_source_filename(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=self.allowlist):
            conn = Connector.objects.create(
                name="local",
                connector_type=Connector.ConnectorType.LOCAL_DIRECTORY,
                config={"base_path": str(self.base)},
            )
            job = IngestionJob.objects.create(
                name="merge",
                source_id="feed-merge",
                connector=conn,
                template=self._template("feed-merge"),
                status=IngestionJob.Status.READY,
            )
            IngestionJobInput.objects.create(job=job, remote_path="a.csv", original_filename="a.csv")
            IngestionJobInput.objects.create(job=job, remote_path="b.csv", original_filename="b.csv")
            run = IngestionJobRun.objects.create(job=job)
            stats = execute_merged_ingestion_run(run)
            self.assertEqual(stats["transaction_count"], 2)
            self.assertEqual(Transaction.objects.filter(source_id="feed-merge").count(), 2)
            names = set(Transaction.objects.filter(source_id="feed-merge").values_list("source_filename", flat=True))
            self.assertEqual(names, {"a.csv", "b.csv"})


class JobOpsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(self.user)

    def test_sources_url_redirects_to_job_create(self):
        response = self.client.get("/ops/sources/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ops/jobs/new", response["Location"])
