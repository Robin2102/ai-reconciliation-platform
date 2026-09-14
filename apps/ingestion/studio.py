"""Shared mapping-studio helpers used by the ops UI (not Django admin)."""

from apps.ingestion.models import ColumnMapping, IngestFile, MappingTemplate
from apps.ingestion.profiling import profile_csv

DATE_FORMAT_CHOICES = [
    "",
    "DD/MM/YYYY",
    "DD-MM-YYYY",
    "YYYY-MM-DD",
    "MM/DD/YYYY",
    "ISO",
    "YYYY-MM-DD HH:MM:SS",
    "DD/MM/YYYY HH:MM:SS",
]

GENERATED_COLUMNS = [
    {
        "name": "transaction_date",
        "meaning": "Date-only copy of the mapped transaction date (Timestamp or Day+Month+Year).",
    },
    {
        "name": "uploaded_date",
        "meaning": "When this file was staged (not a source column).",
    },
    {
        "name": "txn_type",
        "meaning": "CR or DR inferred from signed amount or a type-like column (DrCr, C/D). You do not map this.",
    },
    {
        "name": "reconciled_date",
        "meaning": "Null at ingest; set when auto-matched or when an exception is closed.",
    },
    {
        "name": "reconciled_by",
        "meaning": "Null at ingest; System when auto-matched; Django username when an exception is manually closed.",
    },
]

ROLE_LABELS = {
    "none": "None",
    "external_ref": "Reference",
    "timestamp": "Transaction date (required)",
    "date_year": "Transaction date — year",
    "date_month": "Transaction date — month",
    "date_day": "Transaction date — day",
    "time": "Time of day (optional)",
    "cr_amount": "Credit amount",
    "dr_amount": "Debit amount",
    "amount": "Amount",
    "txn_type": "Txn type (optional)",
    "currency": "Currency",
    "description": "Description",
    "ignore": "Ignore",
}

TRANSACTION_DATE_ROLES = frozenset({"timestamp", "date_year", "date_month", "date_day", "time"})


def mapping_role_choices():
    return [(value, ROLE_LABELS.get(value, label)) for value, label in ColumnMapping.Role.choices]


def seed_or_load_template(ingest_file: IngestFile, profile: dict) -> MappingTemplate:
    template = MappingTemplate.objects.filter(source_id=ingest_file.source_id).order_by("-updated_at").first()
    if template is None:
        template = MappingTemplate.objects.create(
            name=f"{ingest_file.source_id} mapping",
            source_id=ingest_file.source_id,
            default_currency="INR",
        )
    existing = {c.source_header: c for c in template.columns.all()}
    headers = profile["headers"]
    template.columns.exclude(source_header__in=headers).delete()
    for col in profile["columns"]:
        header = col["source_header"]
        if header in existing:
            mapped = existing[header]
            if mapped.role == ColumnMapping.Role.TIMESTAMP and col.get("date_format"):
                mapped.date_format = col["date_format"]
                mapped.detected_type = col["detected_type"]
                mapped.save(update_fields=["date_format", "detected_type"])
            continue
        ColumnMapping.objects.create(
            template=template,
            source_header=header,
            detected_type=col["detected_type"],
            role=col["role"],
            mapped_name=col["mapped_name"],
            date_format=col.get("date_format") or "",
            pii=col.get("pii") or ColumnMapping.Pii.NONE,
            extra={"trim": col.get("trim", True)},
        )
    return MappingTemplate.objects.prefetch_related("columns").get(pk=template.pk)


def save_mapping_from_post(request, template: MappingTemplate, headers: list[str]) -> MappingTemplate:
    template.name = (request.POST.get("template_name") or template.name).strip() or template.name
    template.default_currency = (request.POST.get("default_currency") or template.default_currency).strip().upper()
    template.normalize_headers = request.POST.get("normalize_headers") == "on"
    template.save()
    by_header = {c.source_header: c for c in template.columns.all()}
    for i, header in enumerate(headers):
        col = by_header.get(header) or ColumnMapping(template=template, source_header=header)
        col.detected_type = request.POST.get(f"col-{i}-detected_type", col.detected_type or "string")
        col.role = request.POST.get(f"col-{i}-role", col.role or ColumnMapping.Role.NONE)
        col.mapped_name = request.POST.get(f"col-{i}-mapped_name", col.mapped_name)
        col.null_policy = request.POST.get(f"col-{i}-null_policy", col.null_policy or ColumnMapping.NullPolicy.KEEP)
        col.date_format = request.POST.get(f"col-{i}-date_format", "") or ""
        col.pii = request.POST.get(f"col-{i}-pii", col.pii or ColumnMapping.Pii.NONE)
        col.extra = {"trim": request.POST.get(f"col-{i}-trim") == "on"}
        col.save()
    return MappingTemplate.objects.prefetch_related("columns").get(pk=template.pk)


def mapping_page_context(ingest_file: IngestFile, highlight_transaction_date: bool = False) -> dict:
    profile = profile_csv(ingest_file.path)
    template = seed_or_load_template(ingest_file, profile)
    columns = list(template.columns.all())
    col_by_header = {c.source_header: c for c in columns}
    column_rows = []
    for i, header in enumerate(profile["headers"]):
        col = col_by_header.get(header)
        extra = (col.extra or {}) if col else {}
        role = col.role if col else "none"
        column_rows.append(
            {
                "index": i,
                "header": header,
                "mapping": col,
                "trim": extra.get("trim", True),
                "date_role_highlight": highlight_transaction_date and role in TRANSACTION_DATE_ROLES,
            }
        )
    return {
        "ingest_file": ingest_file,
        "template": template,
        "profile": profile,
        "column_rows": column_rows,
        "sample_matrix": [[row.get(h, "") for h in profile["headers"]] for row in profile["sample_rows"]],
        "role_choices": mapping_role_choices(),
        "highlight_transaction_date": highlight_transaction_date,
        "type_choices": ColumnMapping.DetectedType.choices,
        "null_choices": ColumnMapping.NullPolicy.choices,
        "pii_choices": ColumnMapping.Pii.choices,
        "date_format_choices": DATE_FORMAT_CHOICES,
        "generated_columns": GENERATED_COLUMNS,
    }
