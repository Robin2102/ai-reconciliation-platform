from typing import Any

from apps.adaptors.base import DataSourceAdapter
from apps.adaptors.heuristic_normalize import heuristic_normalize
from apps.adaptors.pdf_io import extract_pdf_rows
from apps.adaptors.registry import register_adapter


@register_adapter("pdf")
class PdfAdapter(DataSourceAdapter):
    """
    PDF table extract (pdfplumber). Scanned/image PDFs need OCR (not in V1).
    Ops ingest uses mapping templates like CSV/Excel.
    """

    def extract(self, source_input):
        return extract_pdf_rows(source_input)

    def normalize(self, raw_record: dict[str, Any], source_id: str = "pdf_source"):
        return heuristic_normalize(raw_record, source_id=source_id or "pdf_source")
