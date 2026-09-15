"""Encrypt connector secrets at rest (Fernet, same key as PII in dev)."""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.PII_FERNET_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_secrets(data: dict) -> str:
    payload = json.dumps(data or {}).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_secrets(ciphertext: str) -> dict:
    if not ciphertext:
        return {}
    try:
        raw = _fernet().decrypt(ciphertext.encode("ascii"))
    except InvalidToken:
        return {}
    parsed = json.loads(raw.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {}
