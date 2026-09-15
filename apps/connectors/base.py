"""Connector driver contract (transport layer — not format adaptors)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestResult:
    ok: bool
    message: str
    latency_ms: float | None = None


@dataclass
class ListEntry:
    name: str
    path: str
    entry_type: str  # "file" | "dir"
    size: int | None = None
    modified_at: str | None = None


@dataclass
class ListResult:
    path: str
    entries: list[ListEntry] = field(default_factory=list)
    parent_path: str | None = None


@dataclass
class FetchResult:
    ok: bool
    local_path: Path | None = None
    message: str = ""


class ConnectorDriver(ABC):
    connector_type: str

    @abstractmethod
    def validate_config(self, config: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self, config: dict, secrets: dict) -> TestResult:
        raise NotImplementedError

    @abstractmethod
    def list_entries(self, config: dict, secrets: dict, path: str = "") -> ListResult:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, config: dict, secrets: dict, remote_path: str, dest: Path) -> FetchResult:
        raise NotImplementedError
