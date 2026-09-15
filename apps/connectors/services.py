from __future__ import annotations

from pathlib import Path

from apps.connectors.base import FetchResult, ListResult, TestResult
from apps.connectors.models import Connector
from apps.connectors.path_safety import PathNotAllowedError
from apps.connectors.registry import get_connector_driver


def _driver_for(connector: Connector):
    if not connector.is_active:
        raise ValueError("Connector is disabled.")
    if connector.connector_type not in ("local_directory",):
        raise ValueError(f"Connector type '{connector.connector_type}' is not enabled in this release.")
    driver = get_connector_driver(connector.connector_type)
    driver.validate_config(connector.config or {})
    return driver


def test_connector(connector: Connector) -> TestResult:
    try:
        driver = _driver_for(connector)
    except (PathNotAllowedError, ValueError) as exc:
        return TestResult(False, str(exc))
    return driver.test_connection(connector.config or {}, connector.get_secrets())


def browse_connector(connector: Connector, path: str = "") -> ListResult:
    driver = _driver_for(connector)
    return driver.list_entries(connector.config or {}, connector.get_secrets(), path=path)


def fetch_connector_file(connector: Connector, remote_path: str, dest: Path) -> FetchResult:
    driver = _driver_for(connector)
    return driver.fetch(connector.config or {}, connector.get_secrets(), remote_path, dest)
