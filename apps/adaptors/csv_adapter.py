import csv
import io
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional, TextIO, Union

from .base import CanonicalRecord, DataSourceAdapter
from .registry import register_adapter


@register_adapter("csv")
class CsvAdapter(DataSourceAdapter):
    """
    Concrete adapter for CSV data sources. Reads raw CSV rows, maps field headers
    to canonical contract names, cleans currency amounts, parses timestamps, and
    produces CanonicalRecord instances.
    """

    def extract(self, source_input: Union[str, Path, TextIO, bytes, io.StringIO]) -> Iterable[dict[str, Any]]:
        """
        Pull raw records from a CSV file path, open text handle, bytes, or StringIO.
        Yields raw row dictionaries.
        """
        if isinstance(source_input, (str, Path)):
            with open(source_input, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    yield dict(row)
        elif isinstance(source_input, bytes):
            text = source_input.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                yield dict(row)
        elif hasattr(source_input, "read"):
            # Handle text stream or StringIO
            content = source_input.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                yield dict(row)
        else:
            raise ValueError(f"Unsupported CSV source_input type: {type(source_input)}")

    def normalize(self, raw_record: dict[str, Any], source_id: str = "csv_source") -> CanonicalRecord:
        """
        Map a raw CSV record dictionary into a validated CanonicalRecord.
        Computes credit/debit amounts and clean field representations.
        """
        # Clean dictionary keys (lowercase and stripped for matching)
        norm_keys = {str(k).strip().lower(): v for k, v in raw_record.items() if k is not None}

        # 1. External Reference Mapping
        external_ref = self._find_key_value(
            norm_keys,
            ["external_ref", "txn_id", "transaction_id", "ref_no", "reference", "voucher_no", "id", "seq_no"],
        )
        if not external_ref:
            external_ref = f"REF-{uuid.uuid4().hex[:8].upper()}"

        # 2. Credit and Debit Amounts Calculation
        cr_amount, dr_amount = self._extract_amounts(norm_keys)

        # 3. Currency Mapping
        currency = self._find_key_value(norm_keys, ["currency", "curr"]) or "INR"

        # 4. Timestamp Parsing
        date_str = self._find_key_value(norm_keys, ["timestamp", "date", "trans_date", "posting_date", "txn_date"])
        timestamp = self._parse_timestamp(date_str)

        # 5. Narrative / Description Mapping
        description = self._find_key_value(norm_keys, ["description", "narrative", "remarks", "memo", "particulars"])

        return CanonicalRecord(
            source_id=source_id or "csv_source",
            external_ref=str(external_ref).strip(),
            cr_amount=cr_amount,
            dr_amount=dr_amount,
            currency=str(currency).strip().upper(),
            timestamp=timestamp,
            description=str(description).strip() if description else None,
            raw_payload=raw_record,
        )

    def _extract_amounts(self, norm_keys: dict[str, Any]) -> tuple[Decimal, Decimal]:
        """Extract credit and debit amounts from raw row dict keys."""
        cr_val = self._find_key_value(norm_keys, ["cr_amount", "credit_amount", "credit_amt", "credit", "cr", "amount_cr"])
        dr_val = self._find_key_value(norm_keys, ["dr_amount", "debit_amount", "debit_amt", "debit", "dr", "amount_dr"])

        cr_amount = self._clean_amount(cr_val)
        dr_amount = self._clean_amount(dr_val)

        # Check if single 'amount' column with 'type' / 'dc_flag'
        if cr_amount == Decimal("0.00") and dr_amount == Decimal("0.00"):
            single_amt_val = self._find_key_value(norm_keys, ["amount", "amt", "val", "value"])
            type_val = self._find_key_value(norm_keys, ["type", "dc_flag", "cr_dr", "d_c_flag", "txn_type"])
            if single_amt_val is not None:
                amt = self._clean_amount(single_amt_val)
                type_str = str(type_val).strip().upper() if type_val else ""
                if "DR" in type_str or type_str == "D" or amt < Decimal("0.00"):
                    dr_amount = abs(amt)
                else:
                    cr_amount = abs(amt)

        return cr_amount, dr_amount

    def _find_key_value(self, norm_keys: dict[str, Any], candidates: list[str]) -> Optional[Any]:
        """Find the first matching candidate key in normalized dict keys."""
        for candidate in candidates:
            if candidate in norm_keys and norm_keys[candidate] is not None:
                val = str(norm_keys[candidate]).strip()
                if val:
                    return norm_keys[candidate]
        return None

    def _clean_amount(self, val: Any) -> Decimal:
        """Strip currency symbols, commas, whitespace and parse into a Decimal."""
        if val is None:
            return Decimal("0.00")
        s = str(val).strip()
        if not s:
            return Decimal("0.00")

        # Strip currency symbols (e.g. ₨, $, €, ₹) and commas
        cleaned = re.sub(r"[^\d\.\-\+]", "", s)
        if not cleaned or cleaned in ["-", "+", "."]:
            return Decimal("0.00")

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0.00")

    def _parse_timestamp(self, val: Any) -> datetime:
        """Attempt to parse datetime from multiple common string formats."""
        if not val:
            return datetime.now(timezone.utc)
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)

        s = str(val).strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%Y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return datetime.now(timezone.utc)

