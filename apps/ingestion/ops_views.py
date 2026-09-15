from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.ingestion.ingest_results import ingest_result_rows
from apps.ingestion.models import IngestFile, IngestionJobRun


@staff_member_required(login_url="ops-login")
def ops_home(request):
    """Ops entry: ingestion jobs are the only upload / ingest workflow."""
    return redirect("ops-connectors")


@staff_member_required(login_url="ops-login")
def ingest_results(request, file_id: int):
    ingest_file = get_object_or_404(IngestFile, pk=file_id)
    if ingest_file.status != IngestFile.Status.DONE:
        messages.info(request, "Normalized rows are available after a successful ingestion job run.")
        job_run = (
            IngestionJobRun.objects.filter(primary_ingest_file_id=ingest_file.pk)
            .select_related("job")
            .order_by("-id")
            .first()
        )
        if job_run:
            return redirect("ops-job-detail", job_id=job_run.job_id)
        return redirect("ops-jobs")

    job_run = (
        IngestionJobRun.objects.filter(primary_ingest_file_id=ingest_file.pk)
        .select_related("job")
        .order_by("-id")
        .first()
    )
    ctx = ingest_result_rows(ingest_file)
    return render(
        request,
        "ops/ingest_results.html",
        {
            "ingest_file": ingest_file,
            "job_run": job_run,
            **ctx,
        },
    )
