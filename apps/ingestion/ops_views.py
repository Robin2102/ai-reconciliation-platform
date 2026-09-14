from pathlib import Path

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.ingestion.mapping import validate_template
from apps.ingestion.models import IngestFile
from apps.ingestion.services import stage_uploaded_file
from apps.ingestion.studio import mapping_page_context, save_mapping_from_post
from apps.ingestion.tasks import ingest_file_task


class IngestUploadForm(forms.Form):
    file = forms.FileField(label="CSV file")
    source_type = forms.CharField(initial="csv", max_length=50, label="Source type")
    source_id = forms.CharField(
        required=False,
        max_length=100,
        label="Source ID",
        help_text="Defaults to the filename. Reused to load last month’s mapping template.",
    )


@staff_member_required(login_url="ops-login")
def ingest_home(request):
    form = IngestUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        source_type = form.cleaned_data["source_type"]
        source_id = form.cleaned_data.get("source_id") or Path(uploaded.name).stem
        try:
            ingest_file = stage_uploaded_file(uploaded, source_type, source_id)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.info(request, f"Staged {ingest_file.original_name}. Map columns, then run ingest.")
            return redirect("ops-mapping", file_id=ingest_file.pk)

    files = IngestFile.objects.all()[:25]
    return render(
        request,
        "ops/ingest_home.html",
        {
            "form": form,
            "ingest_files": files,
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
def ingest_file_list(request):
    files = IngestFile.objects.all()[:25]
    return render(
        request,
        "ops/_file_list.html",
        {"ingest_files": files, "poll": any(f.status == IngestFile.Status.INGESTING for f in files)},
    )
