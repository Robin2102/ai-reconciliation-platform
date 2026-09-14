import io
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.ingestion.services import infer_source_type, ingest_source
from apps.reconciliation.models import Transaction


class InferSourceTypeTests(TestCase):
    def test_txt_extension_defaults_to_txt_adapter(self):
        self.assertEqual(infer_source_type("ledger.txt", "csv"), "txt")

    def test_csv_extension_stays_csv(self):
        self.assertEqual(infer_source_type("ledger.csv", "csv"), "csv")

    def test_explicit_txt_respected(self):
        self.assertEqual(infer_source_type("data.csv", "txt"), "txt")

    def test_xlsx_extension_defaults_to_xlsx(self):
        self.assertEqual(infer_source_type("report.xlsx", "csv"), "xlsx")

    def test_pdf_extension_defaults_to_pdf(self):
        self.assertEqual(infer_source_type("stmt.pdf", "csv"), "pdf")


class KafkaPublishTests(TestCase):
    @override_settings(KAFKA_ENABLED=True)
    @patch("apps.ingestion.services.publish_record_ingested")
    def test_ingest_source_publishes_after_commit(self, publish):
        from apps.ingestion.tests.fixtures import BANK_SEP_CSV

        ingest_source("csv", "hdfc-sep", io.BytesIO(BANK_SEP_CSV.encode("utf-8")))
        publish.assert_called_once()
        payload = publish.call_args[0][0]
        self.assertEqual(payload["source_id"], "hdfc-sep")
        self.assertEqual(payload["source_type"], "csv")
        self.assertEqual(payload["transaction_count"], 2)
        self.assertEqual(len(payload["transaction_ids"]), 2)
        self.assertEqual(Transaction.objects.count(), 2)
