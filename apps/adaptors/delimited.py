"""Shared delimited-row extract (CSV, TXT, bank exports)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable, TextIO, Union

_SNIFF_DELIMITERS = ",;\t|"
_SNIFF_BYTES = 8192

SourceInput = Union[str, Path, TextIO, bytes, io.StringIO]


def csv_dict_reader(text_stream: TextIO) -> csv.DictReader:
    """
    DictReader that sniffs comma / semicolon / tab / pipe.

    European bank exports often use `;`. Default csv.excel would treat the
    whole header row as one column and overflow varchar on mapping seed.
    """
    start = text_stream.tell() if hasattr(text_stream, "tell") else 0
    sample = text_stream.read(_SNIFF_BYTES)
    if hasattr(text_stream, "seek"):
        text_stream.seek(start)
    else:
        text_stream = io.StringIO(sample + text_stream.read())
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_SNIFF_DELIMITERS)
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(text_stream, dialect=dialect)


def extract_delimited_rows(source_input: SourceInput) -> Iterable[dict[str, Any]]:
    """Yield header-keyed rows from a delimited text file or stream."""
    if isinstance(source_input, (str, Path)):
        with open(source_input, mode="r", encoding="utf-8-sig", newline="") as handle:
            reader = csv_dict_reader(handle)
            for row in reader:
                yield dict(row)
        return
    if isinstance(source_input, bytes):
        text = source_input.decode("utf-8-sig")
        reader = csv_dict_reader(io.StringIO(text))
        for row in reader:
            yield dict(row)
        return
    if hasattr(source_input, "read"):
        content = source_input.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        reader = csv_dict_reader(io.StringIO(content))
        for row in reader:
            yield dict(row)
        return
    raise ValueError(f"Unsupported delimited source_input type: {type(source_input)}")
