"""CSV header + sample profiler. No pandas — csv + type heuristics."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from apps.adaptors.delimited import csv_dict_reader, open_delimited_text
from apps.adaptors.excel_io import extract_excel_rows

SAMPLE_ROWS = 50

DATE_FORMATS = [
    ("%Y-%m-%d", "YYYY-MM-DD"),
    ("%Y%m%d", "YYYYMMDD"),
    ("%d/%m/%Y", "DD/MM/YYYY"),
    ("%d-%m-%Y", "DD-MM-YYYY"),
    ("%m/%d/%Y", "MM/DD/YYYY"),
    ("%Y-%m-%dT%H:%M:%S", "ISO"),
    ("%Y-%m-%d %H:%M:%S", "YYYY-MM-DD HH:MM:SS"),
    ("%d/%m/%Y %H:%M:%S", "DD/MM/YYYY HH:MM:SS"),
]

ROLE_HINTS = [
    (("tran_id", "txn_id", "transaction_id", "external_ref", "ref", "reference"), "external_ref"),
    (("tran_date", "txn_date", "value_date", "posting_date", "timestamp", "date", "ba_tran_date"), "timestamp"),
    (("year", "txn_year", "date_year"), "date_year"),
    (("month", "txn_month", "date_month"), "date_month"),
    (("day", "txn_day", "date_day"), "date_day"),
    (("time", "txn_time", "value_time"), "time"),
    (("credit", "cr_amount", "cr"), "cr_amount"),
    (("debit", "dr_amount", "dr"), "dr_amount"),
    (("amount", "amt", "txn_amount"), "amount"),
    (("txn_type", "tran_type", "type", "dr_cr", "drcr", "cd", "dcr"), "txn_type"),
    (("currency", "ccy", "curr"), "currency"),
    (("description", "narrative", "remarks", "narration", "particulars"), "description"),
]

PII_HINTS = ("card_number", "card_no", "pan", "account_number", "acct_no", "ssn")


def normalize_header(header: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return slug or "column"


def _headers_with_full_date_column(headers: list[str]) -> bool:
    for header in headers:
        key = normalize_header(header)
        if key in {"date", "tran_date", "txn_date", "value_date", "posting_date", "timestamp", "ba_tran_date"}:
            return True
    return False


def suggest_role(header: str, headers: list[str] | None = None) -> str:
    key = normalize_header(header)
    if headers and _headers_with_full_date_column(headers):
        if key in {"day", "txn_day", "date_day", "month", "txn_month", "date_month", "year", "txn_year", "date_year"}:
            return "none"
    for aliases, role in ROLE_HINTS:
        if key in aliases:
            return role
    return "none"


def suggest_pii(header: str) -> str:
    key = normalize_header(header)
    return "encrypt" if any(h in key for h in PII_HINTS) else "none"


def _looks_int(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+", value.strip()))


def _looks_decimal(value: str) -> bool:
    cleaned = re.sub(r"[^\d.\-+]", "", value.strip())
    if not cleaned or cleaned in {"-", "+", "."}:
        return False
    try:
        Decimal(cleaned)
    except InvalidOperation:
        return False
    return "." in cleaned or bool(re.search(r"[^\d.\-+]", value))


def _looks_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    for fmt, label in DATE_FORMATS:
        try:
            datetime.strptime(text, fmt)
            return label
        except ValueError:
            continue
    return None


def infer_column_type(samples: list[str]) -> tuple[str, str]:
    nonempty = [str(s).strip() for s in samples if str(s).strip()]
    if not nonempty:
        return "string", ""
    date_votes: dict[str, int] = {}
    int_n = dec_n = 0
    for raw in nonempty:
        label = _looks_date(raw)
        if label:
            date_votes[label] = date_votes.get(label, 0) + 1
            continue
        if _looks_int(raw):
            int_n += 1
        elif _looks_decimal(raw):
            dec_n += 1
    n = len(nonempty)
    if date_votes and max(date_votes.values()) >= n * 0.6:
        return "date", max(date_votes, key=date_votes.get)
    if int_n >= n * 0.8:
        return "integer", ""
    if (int_n + dec_n) >= n * 0.8:
        return "decimal", ""
    return "string", ""


def _profile_from_row_dicts(headers: list[str], rows: list[dict[str, str]]) -> dict[str, Any]:
    columns = []
    for header in headers:
        samples = [r.get(header, "") for r in rows]
        detected, date_format = infer_column_type(samples)
        mapped = normalize_header(header)
        columns.append(
            {
                "source_header": header,
                "detected_type": detected,
                "date_format": date_format,
                "mapped_name": mapped,
                "role": suggest_role(header, headers),
                "pii": suggest_pii(header),
                "null_policy": "keep",
                "trim": True,
            }
        )
    return {"headers": headers, "columns": columns, "sample_rows": rows}


def profile_delimited_file(path: str | Path, sample_rows: int = SAMPLE_ROWS) -> dict[str, Any]:
    reader = csv_dict_reader(open_delimited_text(path))
    headers = list(reader.fieldnames or [])
    rows: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if i >= sample_rows:
            break
        rows.append({h: (row.get(h) or "") for h in headers})
    return _profile_from_row_dicts(headers, rows)


def profile_excel_file(path: str | Path, sample_rows: int = SAMPLE_ROWS) -> dict[str, Any]:
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    for i, row in enumerate(extract_excel_rows(path)):
        if not headers:
            headers = list(row.keys())
        if i >= sample_rows:
            break
        rows.append({h: str(row.get(h) or "") for h in headers})
    return _profile_from_row_dicts(headers, rows)


def profile_staged_file(path: str | Path, source_type: str, sample_rows: int = SAMPLE_ROWS) -> dict[str, Any]:
    from apps.ingestion.services import profiler_source_type

    kind = profiler_source_type(path, source_type)
    if kind == "xlsx":
        return profile_excel_file(path, sample_rows=sample_rows)
    return profile_delimited_file(path, sample_rows=sample_rows)


def profile_csv(path: str | Path, sample_rows: int = SAMPLE_ROWS) -> dict[str, Any]:
    """Alias for staged CSV/TXT files (same delimited profiler)."""
    return profile_delimited_file(path, sample_rows=sample_rows)
