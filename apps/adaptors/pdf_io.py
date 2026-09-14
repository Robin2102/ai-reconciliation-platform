"""Extract tabular rows from PDF bank/ledger exports (pdfplumber)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Union

import pdfplumber

SourceInput = Union[str, Path, bytes, BinaryIO]


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _header_label(raw: Any, index: int) -> str:
    text = _cell_str(raw)
    return text if text else f"column_{index + 1}"


def _row_empty(cells: list[Any]) -> bool:
    return not any(_cell_str(c) for c in cells)


def _tables_to_rows(tables: list[list[list[Any | None]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        headers = [_header_label(cell, i) for i, cell in enumerate(table[0])]
        if not any(h and not h.startswith("column_") for h in headers):
            continue
        for data_row in table[1:]:
            if not data_row or _row_empty(data_row):
                continue
            padded = list(data_row) + [None] * max(0, len(headers) - len(data_row))
            rows.append({headers[i]: _cell_str(padded[i]) for i in range(len(headers))})
    return rows


def iter_pdf_dict_rows(file_stream: BinaryIO) -> Iterable[dict[str, Any]]:
    with pdfplumber.open(file_stream) as pdf:
        all_tables: list[list[list[Any | None]]] = []
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if table:
                    all_tables.append(table)
        for row in _tables_to_rows(all_tables):
            yield row


def extract_pdf_rows(source_input: SourceInput) -> Iterable[dict[str, Any]]:
    if isinstance(source_input, (str, Path)):
        with open(source_input, mode="rb") as handle:
            for row in iter_pdf_dict_rows(handle):
                yield row
        return
    if isinstance(source_input, bytes):
        for row in iter_pdf_dict_rows(io.BytesIO(source_input)):
            yield row
        return
    if hasattr(source_input, "read"):
        content = source_input.read()
        if not isinstance(content, bytes):
            raise ValueError("PDF source stream must yield bytes.")
        for row in iter_pdf_dict_rows(io.BytesIO(content)):
            yield row
        return
    raise ValueError(f"Unsupported PDF source_input type: {type(source_input)}")
