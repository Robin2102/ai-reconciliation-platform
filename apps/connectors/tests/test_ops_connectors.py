import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.connectors.models import Connector


class ConnectorOpsTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)
        (self.base / "sample.csv").write_text("x\n1\n", encoding="utf-8")
        User = get_user_model()
        self.user = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(self.user)

    def test_create_test_and_browse(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=[str(self.base)]):
            create_url = reverse("ops-connector-create")
            response = self.client.post(
                create_url,
                {"name": "Ops local", "base_path": str(self.base), "is_active": True},
            )
            self.assertEqual(response.status_code, 302)
            connector = Connector.objects.get(name="Ops local")

            test_url = reverse("ops-connector-test", kwargs={"connector_id": connector.pk})
            self.client.post(test_url)
            detail = self.client.get(reverse("ops-connector-detail", kwargs={"connector_id": connector.pk}))
            self.assertContains(detail, "Readable directory")

            browse_api = reverse("ops-connector-browse-api", kwargs={"connector_id": connector.pk})
            data = self.client.get(browse_api).json()
            self.assertTrue(data["ok"])
            self.assertTrue(any(e["name"] == "sample.csv" for e in data["entries"]))
