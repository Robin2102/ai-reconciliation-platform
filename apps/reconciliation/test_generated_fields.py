from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reconciliation.generated_fields import mark_reconciled_manual, mark_reconciled_system


class GeneratedFieldsTests(TestCase):
    def test_ingest_shape_null_reconciled(self):
        payload = {
            "_generated": {
                "transaction_date": "2022-01-01",
                "reconciled_date": None,
                "reconciled_by": None,
            }
        }
        self.assertIsNone(payload["_generated"]["reconciled_date"])
        self.assertIsNone(payload["_generated"]["reconciled_by"])

    def test_mark_reconciled_system(self):
        payload = {"_generated": {"reconciled_date": None, "reconciled_by": None}}
        when = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        mark_reconciled_system(payload, at=when)
        self.assertEqual(payload["_generated"]["reconciled_by"], "System")
        self.assertIn("2026-09-14", payload["_generated"]["reconciled_date"])

    def test_mark_reconciled_manual(self):
        user = get_user_model().objects.create_user("ops1", password="pass")
        payload = {"_generated": {}}
        mark_reconciled_manual(payload, user)
        self.assertEqual(payload["_generated"]["reconciled_by"], "ops1")
