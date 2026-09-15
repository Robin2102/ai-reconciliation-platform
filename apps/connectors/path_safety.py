"""Resolve paths under connector base and global allowlist."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


class PathNotAllowedError(ValueError):
    pass


def local_allowlist_roots() -> list[Path]:
    roots: list[Path] = []
    for item in getattr(settings, "CONNECTOR_LOCAL_ALLOWLIST", []):
        roots.append(Path(item).resolve())
    upload = getattr(settings, "INGEST_UPLOAD_DIR", None)
    if upload:
        roots.append(Path(upload).resolve())
    staging = getattr(settings, "CONNECTOR_STAGING_ROOT", None)
    if staging:
        roots.append(Path(staging).resolve())
    # dedupe
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def assert_path_allowed(path: Path) -> Path:
    resolved = path.resolve()
    for root in local_allowlist_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise PathNotAllowedError(
        f"Path {resolved} is not under allowed connector roots. "
        "Set CONNECTOR_LOCAL_ALLOWLIST in settings / .env."
    )


def resolve_under_base(base_path: Path, relative: str = "") -> Path:
    base = assert_path_allowed(base_path.resolve())
    rel = (relative or "").strip().lstrip("/")
    if rel in ("", "."):
        target = base
    else:
        if ".." in Path(rel).parts:
            raise PathNotAllowedError("Path must not contain '..'.")
        target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        raise PathNotAllowedError("Path escapes connector base directory.")
    return target
