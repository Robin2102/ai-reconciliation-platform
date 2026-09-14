"""Shared delimited-row extract (CSV, TXT, bank exports)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable, TextIO, Union

_SNIFF_DELIMITERS = ",;\t|"
_SNIFF_BYTES = 8192
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

SourceInput = Union[str, Path, TextIO, bytes, io.StringIO]


def decode_text_bytes(data: bytes) -> str:
    """Decode bank CSV/TXT exports (UTF-8, Windows-1252, Latin-1)."""
    for encoding in _TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def open_delimited_text(path: str | Path) -> TextIO:
    return io.StringIO(decode_text_bytes(Path(path).read_bytes()))


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
        reader = csv_dict_reader(open_delimited_text(source_input))
        for row in reader:
            yield dict(row)
        return
    if isinstance(source_input, bytes):
        reader = csv_dict_reader(io.StringIO(decode_text_bytes(source_input)))
        for row in reader:
            yield dict(row)
        return
    if hasattr(source_input, "read"):
        content = source_input.read()
        if isinstance(content, bytes):
            content = decode_text_bytes(content)
        reader = csv_dict_reader(io.StringIO(content))
        for row in reader:
            yield dict(row)
        return
    raise ValueError(f"Unsupported delimited source_input type: {type(source_input)}")
