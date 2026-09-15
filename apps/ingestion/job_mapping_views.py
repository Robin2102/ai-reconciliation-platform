from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.ingestion.job_inputs import ensure_job_profile_file
from apps.ingestion.mapping import validate_template
from apps.ingestion.models import IngestionJob
from apps.ingestion.studio import (
    mapping_page_context_for_job,
    refresh_ingestion_job_profile,
    save_mapping_from_post,
)

MAPPING_TEMPLATE = "ops/mapping.html"


@staff_member_required(login_url="ops-login")
@require_http_methods(["GET", "POST"])
def job_mapping(request, job_id: int):
    job = get_object_or_404(IngestionJob.objects.prefetch_related("inputs"), pk=job_id)
    try:
        ensure_job_profile_file(job)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("ops-job-detail", job_id=job.pk)

    if request.method == "GET":
        try:
            ctx = mapping_page_context_for_job(job)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("ops-job-detail", job_id=job.pk)
        ctx["cancel_url"] = f"/ops/jobs/{job.pk}/"
        ctx["mapping_post_url"] = request.path
        ctx["hide_run_ingest"] = True
        ctx["job_mapping_refresh_url"] = f"/ops/jobs/{job.pk}/mapping/refresh/"
        return render(request, MAPPING_TEMPLATE, ctx)

    profile = mapping_page_context_for_job(job)
    template = profile["template"]
    headers = profile["profile"]["headers"]
    template = save_mapping_from_post(request, template, headers)
    try:
        validate_template(template, columns=list(template.columns.all()))
    except ValueError as exc:
        messages.error(request, str(exc))
        ctx = mapping_page_context_for_job(job, highlight_transaction_date=True)
        ctx["cancel_url"] = f"/ops/jobs/{job.pk}/"
        ctx["mapping_post_url"] = request.path
        ctx["hide_run_ingest"] = True
        return render(request, MAPPING_TEMPLATE, ctx)

    job.template_id = template.pk
    job.status = IngestionJob.Status.READY
    job.save(update_fields=["template_id", "status"])
    if request.headers.get("HX-Request"):
        return HttpResponse('<p class="flash flash-ok">Template saved.</p>')
    messages.success(request, "Mapping saved. You can run the ingestion job.")
    return redirect("ops-job-detail", job_id=job.pk)


@staff_member_required(login_url="ops-login")
@require_POST
def job_mapping_refresh(request, job_id: int):
    job = get_object_or_404(IngestionJob.objects.prefetch_related("inputs"), pk=job_id)
    try:
        refresh_ingestion_job_profile(job)
        job.status = IngestionJob.Status.DRAFT
        job.save(update_fields=["status"])
        messages.success(
            request,
            "Re-fetched the sample file and refreshed detected columns. Review mapping, then save.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, str(exc).strip() or exc.__class__.__name__)
    return redirect("ops-job-mapping", job_id=job.pk)
