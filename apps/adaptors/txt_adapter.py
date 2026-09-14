from typing import Any

from apps.adaptors.base import DataSourceAdapter
from apps.adaptors.csv_adapter import CsvAdapter
from apps.adaptors.heuristic_normalize import heuristic_normalize
from apps.adaptors.registry import register_adapter


@register_adapter("txt")
class TxtAdapter(DataSourceAdapter):
    """Delimited .txt — same extract as CSV; separate registry key for ops/API."""

    def __init__(self) -> None:
        self._delimited = CsvAdapter()

    def extract(self, source_input):
        return self._delimited.extract(source_input)

    def normalize(self, raw_record: dict[str, Any], source_id: str = "txt_source"):
        return heuristic_normalize(raw_record, source_id=source_id or "txt_source")
