"""Apply a MappingTemplate to a raw CSV row → CanonicalRecord."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.adaptors.base import CanonicalRecord
from apps.ingestion.models import ColumnMapping, MappingTemplate
from apps.ingestion.pii import apply_pii_to_payload
from apps.ingestion.profiling import normalize_header

DATE_FORMAT_TO_STRPTIME = {
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYYMMDD": "%Y%m%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "ISO": "%Y-%m-%dT%H:%M:%S",
    "YYYY-MM-DD HH:MM:SS": "%Y-%m-%d %H:%M:%S",
    "DD/MM/YYYY HH:MM:SS": "%d/%m/%Y %H:%M:%S",
}

TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H%M%S", "%I:%M:%S %p", "%I:%M %p")

CREDIT_MARKERS = {"c", "cr", "credit", "crd", "deposit"}
DEBIT_MARKERS = {"d", "dr", "db", "debit", "withdrawal", "wdl"}
TXN_TYPE_HEADER_HINTS = {
    "txn_type",
    "tran_type",
    "type",
    "dr_cr",
    "drcr",
    "cd",
    "dcr",
    "dc_flag",
}

REF_JOIN = "|"
MONTH_NAME = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTH_ABBR = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}


def _cell(row: dict[str, Any], mapping: ColumnMapping) -> Any:
    value = row.get(mapping.source_header)
    extra = mapping.extra or {}
    if extra.get("trim", True) and isinstance(value, str):
        value = value.strip()
    if mapping.null_policy == ColumnMapping.NullPolicy.EMPTY_AS_NULL and value in ("", None):
        return None
    return value


def _parse_amount(val: Any) -> Decimal:
    if val is None:
        return Decimal("0.00")
    cleaned = re.sub(r"[^\d.\-+]", "", str(val).strip())
    if not cleaned or cleaned in {"-", "+", "."}:
        return Decimal("0.00")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0.00")


def _timestamp_parse_candidates(date_format: str) -> list[tuple[str, str]]:
    """Primary mapped format first, then other known patterns (handles stale template formats)."""
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    primary = DATE_FORMAT_TO_STRPTIME.get(date_format) or (date_format if date_format else "%Y-%m-%d")
    label = date_format or "YYYY-MM-DD"
    if primary and primary not in seen:
        ordered.append((label, primary))
        seen.add(primary)
    for fmt_label, fmt in DATE_FORMAT_TO_STRPTIME.items():
        if fmt in seen:
            continue
        ordered.append((fmt_label, fmt))
        seen.add(fmt)
    return ordered


def _parse_timestamp(val: Any, date_format: str, header: str = "timestamp") -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    text = "" if val is None else str(val).strip()
    if not text:
        raise ValueError(f"Column {header!r} (timestamp) is empty.")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    if re.fullmatch(r"\d{8}", text):
        try:
            parsed = datetime.strptime(text, "%Y%m%d")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    if "T" in text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    last_exc: ValueError | None = None
    for label, fmt in _timestamp_parse_candidates(date_format):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            last_exc = exc
            continue
    shown_fmt = date_format or "%Y-%m-%d"
    raise ValueError(
        f"Column {header!r} (timestamp): could not parse {text!r} with format {shown_fmt}."
    ) from last_exc


def _parse_year(val: Any, header: str) -> int:
    text = "" if val is None else str(val).strip()
    if not text:
        raise ValueError(f"Column {header!r} (date year) is empty.")
    try:
        year = int(float(text))
    except ValueError as exc:
        raise ValueError(f"Column {header!r} (date year): could not parse {text!r}.") from exc
    if 0 <= year < 100:
        year += 2000
    return year


def _parse_month(val: Any, header: str) -> int:
    text = "" if val is None else str(val).strip()
    if not text:
        raise ValueError(f"Column {header!r} (date month) is empty.")
    key = text.lower()
    if key in MONTH_NAME:
        return MONTH_NAME[key]
    if key in MONTH_ABBR:
        return MONTH_ABBR[key]
    try:
        month = int(float(text))
    except ValueError as exc:
        raise ValueError(f"Column {header!r} (date month): could not parse {text!r}.") from exc
    if not 1 <= month <= 12:
        raise ValueError(f"Column {header!r} (date month): {month} is not 1–12.")
    return month


def _parse_day(val: Any, header: str) -> int:
    text = "" if val is None else str(val).strip()
    if not text:
        raise ValueError(f"Column {header!r} (date day) is empty.")
    try:
        day = int(float(text))
    except ValueError as exc:
        raise ValueError(f"Column {header!r} (date day): could not parse {text!r}.") from exc
    if not 1 <= day <= 31:
        raise ValueError(f"Column {header!r} (date day): {day} is not a valid day.")
    return day


def _parse_time_of_day(val: Any, header: str) -> time:
    if isinstance(val, time):
        return val
    text = "" if val is None else str(val).strip()
    if not text:
        raise ValueError(f"Column {header!r} (time) is empty.")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Column {header!r} (time): could not parse {text!r}.")


def _columns_by_role(columns: list[ColumnMapping]) -> dict[str, list[ColumnMapping]]:
    found: dict[str, list[ColumnMapping]] = defaultdict(list)
    for col in columns:
        if col.role in (ColumnMapping.Role.NONE, ColumnMapping.Role.IGNORE):
            continue
        found[col.role].append(col)
    return found


def _join_refs(row: dict[str, Any], mappings: list[ColumnMapping]) -> str:
    parts = []
    for mapping in mappings:
        raw = _cell(row, mapping)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            parts.append(text)
    if not parts:
        raise ValueError("Reference is empty (all mapped ref columns were blank).")
    return REF_JOIN.join(parts)


def _sum_amounts(row: dict[str, Any], mappings: list[ColumnMapping]) -> Decimal:
    total = Decimal("0.00")
    for mapping in mappings:
        total += _parse_amount(_cell(row, mapping))
    return total


def _first_text(row: dict[str, Any], mappings: list[ColumnMapping]) -> str:
    for mapping in mappings:
        raw = _cell(row, mapping)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _resolve_timestamp(row: dict[str, Any], by_role: dict[str, list[ColumnMapping]]) -> datetime:
    ts_cols = by_role.get(ColumnMapping.Role.TIMESTAMP, [])
    year_cols = by_role.get(ColumnMapping.Role.DATE_YEAR, [])
    month_cols = by_role.get(ColumnMapping.Role.DATE_MONTH, [])
    day_cols = by_role.get(ColumnMapping.Role.DATE_DAY, [])
    time_cols = by_role.get(ColumnMapping.Role.TIME, [])

    if ts_cols:
        ts_col = ts_cols[0]
        parsed = _parse_timestamp(_cell(row, ts_col), ts_col.date_format, header=ts_col.source_header)
    elif year_cols and month_cols and day_cols:
        year = _parse_year(_cell(row, year_cols[0]), year_cols[0].source_header)
        month = _parse_month(_cell(row, month_cols[0]), month_cols[0].source_header)
        day = _parse_day(_cell(row, day_cols[0]), day_cols[0].source_header)
        try:
            parsed = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Invalid composed date {year}-{month:02d}-{day:02d}.") from exc
    else:
        raise ValueError("Map a timestamp column, or day + month + year.")

    if time_cols:
        clock = _parse_time_of_day(_cell(row, time_cols[0]), time_cols[0].source_header)
        parsed = parsed.replace(hour=clock.hour, minute=clock.minute, second=clock.second, microsecond=clock.microsecond)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _marker_to_cr_dr(amt: Decimal, marker: str) -> tuple[Decimal, Decimal] | None:
    key = marker.strip().lower()
    if key in CREDIT_MARKERS:
        return abs(amt), Decimal("0.00")
    if key in DEBIT_MARKERS:
        return Decimal("0.00"), abs(amt)
    return None


def _infer_type_marker(row: dict[str, Any], columns: list[ColumnMapping]) -> str:
    for mapping in columns:
        if mapping.role == ColumnMapping.Role.IGNORE:
            continue
        key = normalize_header(mapping.source_header)
        if key not in TXN_TYPE_HEADER_HINTS:
            continue
        raw = _cell(row, mapping)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    for header, value in row.items():
        if header is None or value is None:
            continue
        if normalize_header(str(header)) not in TXN_TYPE_HEADER_HINTS:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _signed_amount_to_cr_dr(amt: Decimal) -> tuple[Decimal, Decimal]:
    if amt < 0:
        return Decimal("0.00"), abs(amt)
    return amt, Decimal("0.00")


def _computed_txn_type(cr: Decimal, dr: Decimal) -> str:
    if cr > 0 and dr == 0:
        return "CR"
    if dr > 0 and cr == 0:
        return "DR"
    if cr == 0 and dr == 0:
        return "ZERO"
    return "MIXED"


def _attach_generated(
    payload: dict,
    timestamp: datetime,
    cr: Decimal,
    dr: Decimal,
    uploaded_at: datetime | None,
    source_filename: str | None = None,
) -> dict:
    out = dict(payload)
    uploaded = None
    if uploaded_at is not None:
        if uploaded_at.tzinfo is None:
            uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)
        uploaded = uploaded_at.astimezone(timezone.utc).isoformat()
    out["_generated"] = {
        "uploaded_date": uploaded,
        "transaction_date": timestamp.date().isoformat(),
        "txn_type": _computed_txn_type(cr, dr),
        "reconciled_date": None,
        "reconciled_by": None,
        "source_filename": (source_filename or "").strip() or None,
    }
    return out


def _resolve_money(
    row: dict[str, Any],
    by_role: dict[str, list[ColumnMapping]],
    columns: list[ColumnMapping],
) -> tuple[Decimal, Decimal]:
    cr_cols = by_role.get(ColumnMapping.Role.CR_AMOUNT, [])
    dr_cols = by_role.get(ColumnMapping.Role.DR_AMOUNT, [])
    amt_cols = by_role.get(ColumnMapping.Role.AMOUNT, [])
    type_cols = by_role.get(ColumnMapping.Role.TXN_TYPE, [])
    if cr_cols and dr_cols:
        return _sum_amounts(row, cr_cols), _sum_amounts(row, dr_cols)
    if not amt_cols:
        raise ValueError("Map credit+debit columns, or a single amount column.")

    amt = _sum_amounts(row, amt_cols)
    marker = _first_text(row, type_cols) if type_cols else _infer_type_marker(row, columns)
    if marker:
        split = _marker_to_cr_dr(amt, marker)
        if split is None:
            raise ValueError(
                f"Unknown txn_type {marker!r}; expected C/D, CR/DR, Cr/Db, credit/debit."
            )
        return split
    return _signed_amount_to_cr_dr(amt)


def validate_template(template: MappingTemplate, columns: list[ColumnMapping] | None = None) -> None:
    cols = columns if columns is not None else list(template.columns.all())
    roles = {c.role for c in cols}
    if ColumnMapping.Role.EXTERNAL_REF not in roles:
        raise ValueError("Map at least one Reference column (multiple refs are joined with '|').")
    has_ts = ColumnMapping.Role.TIMESTAMP in roles
    has_ymd = (
        ColumnMapping.Role.DATE_YEAR in roles
        and ColumnMapping.Role.DATE_MONTH in roles
        and ColumnMapping.Role.DATE_DAY in roles
    )
    if not has_ts and not has_ymd:
        raise ValueError(
            "Select transaction date: map one Timestamp column, or Day + Month + Year (optional Time)."
        )
    has_split = ColumnMapping.Role.CR_AMOUNT in roles and ColumnMapping.Role.DR_AMOUNT in roles
    has_amount = ColumnMapping.Role.AMOUNT in roles
    if not has_split and not has_amount:
        raise ValueError(
            "Map credit and debit (one or more of each, summed), or a single amount column. "
            "Txn type is inferred (signed amount, or a DrCr/C/D column) and is not required."
        )
    if ColumnMapping.Role.CURRENCY not in roles and not (template.default_currency or "").strip():
        raise ValueError("Set a currency column or a default currency on the template.")


def apply_column_mapping(
    row: dict[str, Any],
    template: MappingTemplate,
    source_id: str,
    columns: list[ColumnMapping] | None = None,
    uploaded_at: datetime | None = None,
    source_filename: str | None = None,
) -> CanonicalRecord:
    columns = columns if columns is not None else list(template.columns.all())
    by_role = _columns_by_role(columns)
    ref = _join_refs(row, by_role[ColumnMapping.Role.EXTERNAL_REF])
    timestamp = _resolve_timestamp(row, by_role)
    cr, dr = _resolve_money(row, by_role, columns)

    if ColumnMapping.Role.CURRENCY in by_role:
        currency = _first_text(row, by_role[ColumnMapping.Role.CURRENCY]) or template.default_currency
    else:
        currency = template.default_currency

    description = None
    if ColumnMapping.Role.DESCRIPTION in by_role:
        parts = []
        for mapping in by_role[ColumnMapping.Role.DESCRIPTION]:
            raw = _cell(row, mapping)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                parts.append(text)
        description = REF_JOIN.join(parts) or None

    payload = _attach_generated(
        apply_pii_to_payload(row, columns), timestamp, cr, dr, uploaded_at, source_filename
    )
    return CanonicalRecord(
        source_id=source_id,
        external_ref=ref,
        cr_amount=cr,
        dr_amount=dr,
        currency=currency,
        timestamp=timestamp,
        description=description,
        raw_payload=payload,
    )
