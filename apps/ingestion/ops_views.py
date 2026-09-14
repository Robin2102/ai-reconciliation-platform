from pathlib import Path

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.adaptors.registry import list_registered_adapters
from apps.ingestion.mapping import validate_template
from apps.ingestion.models import IngestFile, MappingTemplate
from apps.ingestion.services import infer_source_type, stage_uploaded_file
from apps.ingestion.ingest_results import ingest_result_rows
from apps.ingestion.studio import mapping_page_context, save_mapping_from_post
from apps.ingestion.tasks import ingest_file_task


_SOURCE_TYPE_LABELS = {
    "csv": "CSV — delimited spreadsheet export",
    "txt": "TXT — delimited text (same parser as CSV)",
    "xlsx": "Excel (.xlsx)",
    "pdf": "PDF — table extract (text-based PDFs)",
}


def source_type_choices():
    return [
        (key, _SOURCE_TYPE_LABELS.get(key, key.upper()))
        for key in list_registered_adapters()
    ]


class IngestUploadForm(forms.Form):
    file = forms.FileField(label="CSV, TXT, XLSX, or PDF file")
    source_type = forms.ChoiceField(
        choices=(),
        initial="csv",
        label="Source type",
        help_text="Pick the adapter. A .txt file is auto-selected as TXT when you leave CSV selected.",
    )
    source_id = forms.CharField(
        required=False,
        max_length=100,
        label="Feed key",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. hdfc-current (optional)",
                "list": "known-feed-keys",
                "autocomplete": "off",
            }
        ),
        help_text=(
            "Stable name for this bank or feed (not shown in the file). "
            "Leave blank to use the file name without extension. "
            "Reusing the same key loads your last saved column mapping."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_type"].choices = source_type_choices()


@staff_member_required(login_url="ops-login")
def ingest_home(request):
    form = IngestUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        source_type = infer_source_type(uploaded.name, form.cleaned_data["source_type"])
        source_id = form.cleaned_data.get("source_id") or Path(uploaded.name).stem
        try:
            ingest_file = stage_uploaded_file(uploaded, source_type, source_id)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.info(request, f"Staged {ingest_file.original_name}. Map columns, then run ingest.")
            return redirect("ops-mapping", file_id=ingest_file.pk)

    files = IngestFile.objects.all()[:25]
    known_feed_keys = list(
        MappingTemplate.objects.order_by("-updated_at").values_list("source_id", flat=True).distinct()[:30]
    )
    return render(
        request,
        "ops/ingest_home.html",
        {
            "form": form,
            "ingest_files": files,
            "known_feed_keys": known_feed_keys,
            "poll": any(f.status == IngestFile.Status.INGESTING for f in files),
        },
    )


@staff_member_required(login_url="ops-login")
@require_http_methods(["GET", "POST"])
def mapping_studio(request, file_id: int):
    ingest_file = get_object_or_404(IngestFile, pk=file_id)
    if request.method == "GET" and not Path(ingest_file.path).exists():
        messages.error(request, "Staged file is missing on disk. Upload again.")
        return redirect("ops-ingest")

    if request.method == "GET":
        return render(request, "ops/mapping.html", mapping_page_context(ingest_file))

    action = request.POST.get("action")
    if action not in {"save", "ingest"}:
        return HttpResponseBadRequest("Unknown action")

    ctx = mapping_page_context(ingest_file)
    template = save_mapping_from_post(request, ctx["template"], ctx["profile"]["headers"])
    ingest_file.status = IngestFile.Status.MAPPED
    ingest_file.save(update_fields=["status", "updated_at"])

    if action == "save":
        if request.headers.get("HX-Request"):
            return HttpResponse('<p class="flash flash-ok">Template saved.</p>')
        messages.success(request, "Mapping template saved.")
        return redirect("ops-mapping", file_id=ingest_file.pk)

    try:
        validate_template(template)
    except ValueError as exc:
        messages.error(request, str(exc))
        highlight = "transaction date" in str(exc).lower()
        return render(
            request,
            "ops/mapping.html",
            mapping_page_context(ingest_file, highlight_transaction_date=highlight),
        )

    ingest_file_task.delay(ingest_file.id, template.id)
    ingest_file.refresh_from_db()
    if ingest_file.status == IngestFile.Status.DONE:
        messages.success(request, f"Ingest finished for {ingest_file.original_name}.")
        return redirect("ops-ingest")
    if ingest_file.status == IngestFile.Status.ERROR:
        messages.error(request, ingest_file.error_message)
        return render(request, "ops/mapping.html", mapping_page_context(ingest_file))
    messages.info(
        request,
        f"Ingest queued for {ingest_file.original_name}. This page updates when the worker finishes.",
    )
    return render(request, "ops/mapping.html", mapping_page_context(ingest_file))


@staff_member_required(login_url="ops-login")
def mapping_job_status(request, file_id: int):
    ingest_file = get_object_or_404(IngestFile, pk=file_id)
    return render(request, "ops/_job_status.html", {"ingest_file": ingest_file})


@staff_member_required(login_url="ops-login")
def ingest_results(request, file_id: int):
    ingest_file = get_object_or_404(IngestFile, pk=file_id)
    if ingest_file.status != IngestFile.Status.DONE:
        messages.info(request, "Normalized rows are available after a successful ingest.")
        return redirect("ops-mapping", file_id=ingest_file.pk)

    ctx = ingest_result_rows(ingest_file)
    return render(
        request,
        "ops/ingest_results.html",
        {
            "ingest_file": ingest_file,
            **ctx,
        },
    )


@staff_member_required(login_url="ops-login")
def ingest_file_list(request):
    files = IngestFile.objects.all()[:25]
    return render(
        request,
        "ops/_file_list.html",
        {"ingest_files": files, "poll": any(f.status == IngestFile.Status.INGESTING for f in files)},
    )
