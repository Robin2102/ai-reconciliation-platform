"""Encrypt tagged PII columns at rest. Ciphertext is not used for matching."""

from __future__ import annotations

import re
from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.PII_FERNET_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_pii(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def last4_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits[-4:] if len(digits) >= 4 else ""


def apply_pii_to_payload(row: dict, columns) -> dict:
    """
    Copy row and replace pii=encrypt fields with Fernet ciphertext.

    Optional last4 is stored as `{header}__last4` for ops display.
    """
    out = dict(row)
    for col in columns:
        if getattr(col, "pii", "none") != "encrypt":
            continue
        raw = out.get(col.source_header)
        if raw is None:
            continue
        text = str(raw)
        if not text.strip():
            continue
        suffix = last4_digits(text)
        out[col.source_header] = encrypt_pii(text)
        if suffix:
            out[f"{col.source_header}__last4"] = suffix
    return out
