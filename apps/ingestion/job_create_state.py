"""Query-string state for the new ingestion job wizard (browse without losing draft)."""

from __future__ import annotations

from urllib.parse import urlencode

from apps.connectors.models import Connector


def job_create_is_fresh(request) -> bool:
    """True when opening a blank wizard (not mid–connector browse)."""
    if request.method != "GET":
        return False
    if request.GET.get("fresh") == "1":
        return True
    g = request.GET
    if g.get("connector") or g.get("path") or g.getlist("selected"):
        return False
    if (g.get("name") or "").strip() or (g.get("source_id") or "").strip():
        return False
    return True


def job_create_get_draft(request) -> dict[str, str]:
    if job_create_is_fresh(request):
        return {
            "default_source_type": "csv",
            "input_mode": "upload",
        }
    g = request.GET
    connector = g.get("connector")
    return {
        "name": (g.get("name") or "").strip(),
        "source_id": (g.get("source_id") or "").strip(),
        "default_source_type": (g.get("default_source_type") or "csv").strip(),
        "input_mode": (g.get("input_mode") or ("connector" if connector else "upload")).strip(),
    }


def job_create_query(request, **updates) -> str:
    g = request.GET
    q: dict[str, str] = {
        "type": str(
            updates.get("type")
            or g.get("type")
            or Connector.ConnectorType.LOCAL_DIRECTORY
        ),
        "connector": str(updates.get("connector") or g.get("connector") or ""),
        "path": str(updates.get("path") if "path" in updates else (g.get("path") or "")),
        "name": str(updates.get("name") if "name" in updates else (g.get("name") or "")),
        "source_id": str(updates.get("source_id") if "source_id" in updates else (g.get("source_id") or "")),
        "default_source_type": str(
            updates.get("default_source_type")
            if "default_source_type" in updates
            else (g.get("default_source_type") or "csv")
        ),
        "input_mode": str(
            updates.get("input_mode")
            if "input_mode" in updates
            else (g.get("input_mode") or ("connector" if g.get("connector") else "upload"))
        ),
    }
    if updates.get("test"):
        q["test"] = "1"
    pairs = [(k, v) for k, v in q.items() if v]
    selected = updates.get("selected")
    if selected is None:
        selected = g.getlist("selected")
    for path in selected:
        if path:
            pairs.append(("selected", path))
    return urlencode(pairs, doseq=True)


def job_create_browse_href(request, path: str = "", **updates) -> str:
    from django.urls import reverse

    if path:
        updates = {**updates, "path": path}
    return f"{reverse('ops-job-create')}?{job_create_query(request, **updates)}"
