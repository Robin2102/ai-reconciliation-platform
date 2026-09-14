import io
from pathlib import Path
from typing import Any, Iterable, TextIO, Union

from apps.adaptors.base import DataSourceAdapter
from apps.adaptors.delimited import extract_delimited_rows
from apps.adaptors.heuristic_normalize import heuristic_normalize
from apps.adaptors.registry import register_adapter


@register_adapter("csv")
class CsvAdapter(DataSourceAdapter):
    """Delimited CSV rows → dict extract; heuristic normalize when no mapping template."""

    def extract(self, source_input: Union[str, Path, TextIO, bytes, io.StringIO]) -> Iterable[dict[str, Any]]:
        return extract_delimited_rows(source_input)

    def normalize(self, raw_record: dict[str, Any], source_id: str = "csv_source"):
        return heuristic_normalize(raw_record, source_id=source_id or "csv_source")
