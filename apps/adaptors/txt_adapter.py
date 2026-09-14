from apps.adaptors.csv_adapter import CsvAdapter
from apps.adaptors.registry import register_adapter


@register_adapter("txt")
class TxtAdapter(CsvAdapter):
    """
    Delimited text exports (.txt): tab, pipe, semicolon, or comma separated.

    Extraction matches CSV (delimiter sniffing). Normalization uses the same
    heuristic path when no mapping template is passed; ops ingest uses templates.
    """
