from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.adaptors.registry import list_registered_adapters
from apps.connectors.models import Connector
from apps.connectors.ops_views import LocalDirectoryConnectorForm
from apps.connectors.services import browse_connector, test_connector
from apps.ingestion.job_create_state import (
    job_create_browse_href,
    job_create_get_draft,
    job_create_is_fresh,
    job_create_query,
)
from apps.ingestion.job_inputs import (
    infer_default_source_type_from_inputs,
    max_job_input_files,
    persist_uploads_to_job_inputs,
)
from apps.ingestion.mapping import validate_template
from apps.ingestion.models import IngestionJob, IngestionJobInput, IngestionJobRun, MappingTemplate
from apps.ingestion.tasks import ingestion_job_run_task

CONNECTOR_TYPE_CARDS = [
    (Connector.ConnectorType.LOCAL_DIRECTORY, "Local directory", True),
    (Connector.ConnectorType.SFTP, "SFTP", False),
    (Connector.ConnectorType.POSTGRES, "PostgreSQL", False),
]


class CreateIngestionJobForm(forms.Form):
    name = forms.CharField(max_length=200, label="Job name")
    source_id = forms.CharField(max_length=100, label="Feed key")
    default_source_type = forms.ChoiceField(choices=[], label="Default file type")
    input_mode = forms.ChoiceField(
        choices=[("upload", "Upload files"), ("connector", "Connector browse")],
        initial="upload",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_source_type"].choices = [(k, k) for k in list_registered_adapters()]


def _connectors_for_type(connector_type: str):
    return Connector.objects.filter(is_active=True, connector_type=connector_type).order_by("name")


@staff_member_required(login_url="ops-login")
def job_home(request):
    jobs = IngestionJob.objects.select_related("connector", "template")[:50]
    return render(request, "ops/jobs_home.html", {"jobs": jobs, "max_files": max_job_input_files()})


@staff_member_required(login_url="ops-login")
def job_create(request):
    connector_type = (
        request.GET.get("type")
        or request.POST.get("connector_type")
        or Connector.ConnectorType.LOCAL_DIRECTORY
    )
    selected_connector_id = request.GET.get("connector") or request.POST.get("connector_id")
    browse_path = (request.GET.get("path") or request.POST.get("browse_path") or "").strip()

    form_initial = job_create_get_draft(request) if request.method == "GET" else None
    form = CreateIngestionJobForm(request.POST or None, initial=form_initial)
    new_connector_form = LocalDirectoryConnectorForm(
        request.POST if request.POST.get("action") == "create_connector" else None,
        prefix="newconn",
    )

    if request.method == "POST" and request.POST.get("action") == "create_connector":
        if connector_type != Connector.ConnectorType.LOCAL_DIRECTORY:
            messages.error(request, "Only local directory connectors can be created in ops for now.")
        elif new_connector_form.is_valid():
            connector = new_connector_form.save(commit=False)
            connector.created_by = request.user
            connector.save()
            messages.success(request, f"Connector “{connector.name}” created. Browse and select files below.")
            return redirect(
                job_create_browse_href(
                    request,
                    type=connector_type,
                    connector=str(connector.pk),
                    input_mode="connector",
                )
            )
        else:
            messages.error(request, "Fix connector errors below.")

    if request.method == "POST" and request.POST.get("action") == "create_job" and form.is_valid():
        uploads = request.FILES.getlist("files")
        remote_paths = [p.strip() for p in request.POST.getlist("remote_paths") if p.strip()]
        mode = form.cleaned_data["input_mode"]
        connector_id = request.POST.get("connector_id") or selected_connector_id
        connector = Connector.objects.filter(pk=connector_id, is_active=True).first() if connector_id else None
        if remote_paths and connector:
            mode = "connector"

        if mode == "upload" and not uploads:
            form.add_error(None, "Choose at least one file to upload.")
        elif mode == "connector" and not remote_paths:
            form.add_error(None, "Select at least one file from the connector browse.")
        elif mode == "connector" and connector is None:
            form.add_error(None, "Select or create a connector, then browse and tick files.")
        elif len(uploads) + len(remote_paths) > max_job_input_files():
            form.add_error(None, f"At most {max_job_input_files()} files per job.")
        else:
            default_type = infer_default_source_type_from_inputs(
                uploads,
                remote_paths,
                fallback=form.cleaned_data["default_source_type"],
            )
            job = IngestionJob.objects.create(
                name=form.cleaned_data["name"],
                source_id=form.cleaned_data["source_id"].strip(),
                default_source_type=default_type,
                connector=connector if remote_paths else None,
                template=None,
                status=IngestionJob.Status.DRAFT,
            )
            created_ok = True
            if uploads:
                try:
                    persist_uploads_to_job_inputs(job, uploads)
                except ValueError as exc:
                    job.delete()
                    form.add_error(None, str(exc))
                    created_ok = False
            if created_ok:
                for i, path in enumerate(remote_paths):
                    IngestionJobInput.objects.create(
                        job=job,
                        order=job.inputs.count(),
                        remote_path=path,
                        original_filename=path.split("/")[-1],
                    )
                messages.success(request, f"Job “{job.name}” created — open Mapping to profile columns, then Run.")
                return redirect("ops-job-mapping", job_id=job.pk)

    browse = None
    browse_error = ""
    test_message = ""
    connector = None
    if selected_connector_id:
        connector = Connector.objects.filter(pk=selected_connector_id, is_active=True).first()
        if connector and connector.connector_type == Connector.ConnectorType.LOCAL_DIRECTORY:
            try:
                browse = browse_connector(connector, browse_path)
            except Exception as exc:
                browse_error = str(exc)
            if request.GET.get("test") == "1":
                result = test_connector(connector)
                test_message = result.message if result.ok else f"Failed: {result.message}"

    if request.method == "POST":
        selected_paths = list(dict.fromkeys(request.POST.getlist("remote_paths")))
    else:
        selected_paths = list(dict.fromkeys(request.GET.getlist("selected")))

    return render(
        request,
        "ops/job_form.html",
        {
            "form": form,
            "new_connector_form": new_connector_form,
            "connector_type_cards": CONNECTOR_TYPE_CARDS,
            "connector_type": connector_type,
            "connectors": _connectors_for_type(connector_type),
            "selected_connector": connector,
            "selected_connector_id": selected_connector_id,
            "browse": browse,
            "browse_error": browse_error,
            "browse_path": browse_path,
            "test_message": test_message,
            "max_files": max_job_input_files(),
            "selected_paths": selected_paths if not job_create_is_fresh(request) else [],
            "job_create_query": job_create_query(request),
            "wizard_fresh": job_create_is_fresh(request),
        },
    )


@staff_member_required(login_url="ops-login")
def job_detail(request, job_id: int):
    job = get_object_or_404(
        IngestionJob.objects.select_related("connector", "template").prefetch_related("inputs"),
        pk=job_id,
    )
    latest_run = job.runs.select_related("primary_ingest_file").first()
    has_files = job.inputs.filter(enabled=True).exists()
    mapping_ready = False
    can_run = False
    mapping_error = ""
    if job.template_id:
        try:
            validate_template(job.template, columns=list(job.template.columns.all()))
            mapping_ready = True
            can_run = has_files
        except ValueError as exc:
            mapping_error = str(exc)
    elif has_files:
        mapping_error = "Open Mapping to profile columns from your files."

    if has_files and job.inputs.filter(remote_path__gt="").exists() and job.connector_id is None:
        mapping_error = "This job lists connector paths but has no connector — create a new job from Ingestion jobs."

    return render(
        request,
        "ops/job_detail.html",
        {
            "job": job,
            "latest_run": latest_run,
            "can_run": can_run,
            "mapping_ready": mapping_ready,
            "mapping_error": mapping_error,
            "has_files": has_files,
            "max_files": max_job_input_files(),
        },
    )


@staff_member_required(login_url="ops-login")
@require_POST
def job_run(request, job_id: int):
    job = get_object_or_404(IngestionJob, pk=job_id)
    if not job.template_id:
        messages.error(request, "Complete mapping before running.")
        return redirect("ops-job-mapping", job_id=job.pk)
    if not job.inputs.filter(enabled=True).exists():
        messages.error(request, "Add at least one input file.")
        return redirect("ops-job-detail", job_id=job.pk)
    try:
        validate_template(job.template, columns=list(job.template.columns.all()))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("ops-job-mapping", job_id=job.pk)
    run = IngestionJobRun.objects.create(job=job, status=IngestionJobRun.Status.QUEUED)
    ingestion_job_run_task.delay(run.pk)
    messages.info(request, "Ingestion job queued (merged ingest + Kafka). Refresh shortly.")
    return redirect("ops-job-detail", job_id=job.pk)


@staff_member_required(login_url="ops-login")
@require_POST
def job_add_connector_files(request, job_id: int):
    job = get_object_or_404(IngestionJob, pk=job_id)
    paths = [p.strip() for p in request.POST.getlist("remote_paths") if p.strip()]
    if job.inputs.count() + len(paths) > max_job_input_files():
        messages.error(request, f"Max {max_job_input_files()} files per job.")
        return redirect("ops-job-detail", job_id=job.pk)
    for path in paths:
        IngestionJobInput.objects.create(
            job=job,
            order=job.inputs.count(),
            remote_path=path,
            original_filename=path.split("/")[-1],
        )
    messages.success(request, f"Added {len(paths)} file(s).")
    return redirect("ops-job-detail", job_id=job.pk)
