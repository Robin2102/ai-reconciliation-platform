from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from apps.connectors.base import ConnectorDriver, FetchResult, ListEntry, ListResult, TestResult
from apps.connectors.path_safety import PathNotAllowedError, assert_path_allowed, resolve_under_base
from apps.connectors.registry import register_connector
from apps.connectors.schemas import LocalDirectoryConfig


@register_connector("local_directory")
class LocalDirectoryDriver(ConnectorDriver):
    connector_type = "local_directory"

    def _base(self, config: dict) -> Path:
        parsed = LocalDirectoryConfig.model_validate(config or {})
        return assert_path_allowed(Path(parsed.base_path).expanduser())

    def validate_config(self, config: dict) -> None:
        LocalDirectoryConfig.model_validate(config or {})
        self._base(config)

    def test_connection(self, config: dict, secrets: dict) -> TestResult:
        started = time.perf_counter()
        try:
            base = self._base(config)
            if not base.is_dir():
                return TestResult(False, f"Not a directory: {base}")
            if not base.exists():
                return TestResult(False, f"Path does not exist: {base}")
            next(base.iterdir(), None)
            ms = (time.perf_counter() - started) * 1000
            return TestResult(True, f"Readable directory ({base})", latency_ms=round(ms, 1))
        except (PathNotAllowedError, ValueError) as exc:
            return TestResult(False, str(exc))

    def list_entries(self, config: dict, secrets: dict, path: str = "") -> ListResult:
        base = self._base(config)
        target = resolve_under_base(base, path)
        if not target.is_dir():
            raise ValueError(f"Not a directory: {path or '/'}")
        entries: list[ListEntry] = []
        for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name.startswith("."):
                continue
            rel = child.relative_to(base).as_posix()
            mtime = None
            if child.exists():
                ts = child.stat().st_mtime
                mtime = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            entries.append(
                ListEntry(
                    name=child.name,
                    path=rel,
                    entry_type="dir" if child.is_dir() else "file",
                    size=child.stat().st_size if child.is_file() else None,
                    modified_at=mtime,
                )
            )
        parent = None
        if path:
            parent_path = Path(path).parent.as_posix()
            parent = parent_path if parent_path != "." else ""
        return ListResult(path=path or "", entries=entries, parent_path=parent)

    def fetch(self, config: dict, secrets: dict, remote_path: str, dest: Path) -> FetchResult:
        base = self._base(config)
        source = resolve_under_base(base, remote_path)
        if not source.is_file():
            return FetchResult(False, message=f"Not a file: {remote_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return FetchResult(True, local_path=dest, message="Copied")
