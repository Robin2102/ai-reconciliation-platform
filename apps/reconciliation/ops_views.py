from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.exceptions.models import ExceptionRecord
from apps.ingestion.models import IngestFile
from apps.reconciliation.project_service import create_recon_project
from apps.reconciliation.recon_models import MatchRule, ReconProject, ReconRun
from apps.reconciliation.rule_templates import RULE_TEMPLATES
from apps.reconciliation.tasks import recon_run_task

MATCH_RESULT_LIMIT = 100


class ReconProjectForm(forms.Form):
    name = forms.CharField(max_length=200, label="Project name")
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    source_ingest = forms.ModelChoiceField(
        queryset=IngestFile.objects.filter(status=IngestFile.Status.DONE),
        label="Source ingest",
        help_text="Completed upload (leg A).",
    )
    target_ingest = forms.ModelChoiceField(
        queryset=IngestFile.objects.filter(status=IngestFile.Status.DONE),
        label="Target ingest",
        help_text="Completed upload (leg B).",
    )


class AddRuleForm(forms.Form):
    name = forms.CharField(max_length=120)
    priority = forms.IntegerField(initial=20, min_value=1, max_value=9999)
    template_key = forms.ChoiceField(
        label="Rule template",
        choices=[(k, v["label"]) for k, v in RULE_TEMPLATES.items()],
    )


@staff_member_required(login_url="ops-login")
def recon_home(request):
    form = ReconProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            project = create_recon_project(
                form.cleaned_data["name"],
                form.cleaned_data.get("description") or "",
                form.cleaned_data["source_ingest"].pk,
                form.cleaned_data["target_ingest"].pk,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Project “{project.name}” is ready to run.")
            return redirect("ops-recon-detail", project_id=project.pk)

    projects = ReconProject.objects.prefetch_related("legs", "runs")[:20]
    return render(
        request,
        "ops/recon_home.html",
        {"form": form, "projects": projects},
    )


@staff_member_required(login_url="ops-login")
def recon_detail(request, project_id: int):
    project = get_object_or_404(
        ReconProject.objects.prefetch_related("legs__ingest_file", "rules"),
        pk=project_id,
    )
    source = project.source_leg()
    target = project.target_leg()
    latest_run = project.runs.prefetch_related("results__source_transaction", "results__target_transaction").first()
    match_results: list = []
    match_results_truncated = False
    if latest_run:
        match_results = list(latest_run.results.all()[:MATCH_RESULT_LIMIT])
        if len(match_results) >= MATCH_RESULT_LIMIT:
            match_results_truncated = latest_run.results.count() > MATCH_RESULT_LIMIT
    return render(
        request,
        "ops/recon_detail.html",
        {
            "project": project,
            "source_leg": source,
            "target_leg": target,
            "latest_run": latest_run,
            "match_results": match_results,
            "match_results_truncated": match_results_truncated,
            "rules": project.rules.all(),
            "rule_templates": RULE_TEMPLATES,
            "open_exceptions": project.exceptions.filter(status=ExceptionRecord.Status.OPEN).count(),
        },
    )


@staff_member_required(login_url="ops-login")
def recon_add_rule(request, project_id: int):
    if request.method != "POST":
        return redirect("ops-recon-detail", project_id=project_id)
    project = get_object_or_404(ReconProject, pk=project_id)
    form = AddRuleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not add rule — check the form.")
        return redirect("ops-recon-detail", project_id=project_id)
    template = RULE_TEMPLATES[form.cleaned_data["template_key"]]
    MatchRule.objects.create(
        project=project,
        name=form.cleaned_data["name"],
        priority=form.cleaned_data["priority"],
        logic_mode=template["logic_mode"],
        definition=template["definition"],
    )
    messages.success(request, f"Rule “{form.cleaned_data['name']}” added.")
    return redirect("ops-recon-detail", project_id=project_id)


@staff_member_required(login_url="ops-login")
def recon_exceptions(request, project_id: int):
    project = get_object_or_404(ReconProject, pk=project_id)
    records = (
        ExceptionRecord.objects.filter(project=project)
        .select_related("transaction", "run")
        .order_by("-created_at")[:500]
    )
    return render(
        request,
        "ops/recon_exceptions.html",
        {"project": project, "records": records},
    )


@staff_member_required(login_url="ops-login")
def recon_run(request, project_id: int):
    if request.method != "POST":
        return redirect("ops-recon-detail", project_id=project_id)

    project = get_object_or_404(ReconProject, pk=project_id)
    if project.source_leg() is None or project.target_leg() is None:
        messages.error(request, "Project is missing a source or target leg.")
        return redirect("ops-recon-detail", project_id=project_id)
    if not project.rules.filter(enabled=True).exists():
        messages.error(request, "Add at least one enabled rule before running.")
        return redirect("ops-recon-detail", project_id=project_id)

    run = ReconRun.objects.create(project=project, status=ReconRun.Status.QUEUED)
    recon_run_task.delay(run.pk)
    messages.info(request, "Reconciliation queued. Refresh this page in a few seconds.")
    return redirect("ops-recon-detail", project_id=project_id)
