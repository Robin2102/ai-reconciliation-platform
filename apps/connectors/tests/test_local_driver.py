import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from apps.connectors.models import Connector
from apps.connectors.path_safety import PathNotAllowedError, resolve_under_base
from apps.connectors.registry import get_connector_driver
from apps.connectors.services import browse_connector, fetch_connector_file, test_connector


class LocalDirectoryDriverTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)
        (self.base / "incoming").mkdir()
        (self.base / "incoming" / "bank.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (self.base / "incoming" / "nested").mkdir()
        self.allowlist = [str(self.base)]

    def _connector(self) -> Connector:
        return Connector.objects.create(
            name="test-local",
            connector_type=Connector.ConnectorType.LOCAL_DIRECTORY,
            config={"base_path": str(self.base)},
        )

    def test_test_connection_ok(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=self.allowlist):
            result = test_connector(self._connector())
            self.assertTrue(result.ok)

    def test_list_and_fetch(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=self.allowlist):
            c = self._connector()
            root = browse_connector(c, "")
            names = {e.name for e in root.entries}
            self.assertIn("incoming", names)

            files = browse_connector(c, "incoming")
            self.assertTrue(any(e.name == "bank.csv" for e in files.entries))

            dest = self.base / "out" / "bank.csv"
            fr = fetch_connector_file(c, "incoming/bank.csv", dest)
            self.assertTrue(fr.ok)
            self.assertTrue(dest.is_file())

    def test_path_traversal_blocked(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=self.allowlist):
            base = Path(self.base)
            with self.assertRaises(PathNotAllowedError):
                resolve_under_base(base, "../outside")

    def test_disallowed_base_rejected(self):
        with override_settings(CONNECTOR_LOCAL_ALLOWLIST=self.allowlist):
            c = Connector.objects.create(
                name="bad",
                connector_type=Connector.ConnectorType.LOCAL_DIRECTORY,
                config={"base_path": "/etc"},
            )
            result = test_connector(c)
            self.assertFalse(result.ok)
