from apps.adaptors.csv_adapter import CsvAdapter
from apps.adaptors.excel_io import extract_excel_rows
from apps.adaptors.registry import register_adapter


@register_adapter("xlsx")
class ExcelAdapter(CsvAdapter):
    """Excel .xlsx: first sheet, row 1 headers; mapping studio applies templates."""

    def extract(self, source_input):
        return extract_excel_rows(source_input)
