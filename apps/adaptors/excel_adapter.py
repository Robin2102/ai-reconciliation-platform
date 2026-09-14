from typing import Any

from apps.adaptors.base import DataSourceAdapter
from apps.adaptors.excel_io import extract_excel_rows
from apps.adaptors.heuristic_normalize import heuristic_normalize
from apps.adaptors.registry import register_adapter


@register_adapter("xlsx")
class ExcelAdapter(DataSourceAdapter):
    """Excel .xlsx — first sheet, row 1 headers."""

    def extract(self, source_input):
        return extract_excel_rows(source_input)

    def normalize(self, raw_record: dict[str, Any], source_id: str = "xlsx_source"):
        return heuristic_normalize(raw_record, source_id=source_id or "xlsx_source")
