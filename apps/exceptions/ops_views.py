from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.exceptions.models import ExceptionRecord
from apps.exceptions.services import (
    ExceptionWorkflowError,
    reject_exception,
    resolve_manual_match,
    resolve_write_off,
    start_investigating,
)
from apps.reconciliation.leg_data import transactions_for_leg
from apps.reconciliation.recon_models import ReconProject


class ExceptionFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + list(ExceptionRecord.Status.choices),
    )
    side = forms.ChoiceField(
        required=False,
        choices=[("", "All sides")] + list(ExceptionRecord.Side.choices),
    )


class ResolveManualMatchForm(forms.Form):
    counterparty_id = forms.IntegerField(label="Opposite leg row", required=True)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class ResolveWriteOffForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), label="Reason")


class RejectForm(forms.Form):
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


def _counterparty_choices(project: ReconProject, record: ExceptionRecord):
    if record.side == ExceptionRecord.Side.SOURCE:
        leg = project.target_leg()
    else:
        leg = project.source_leg()
    if leg is None:
        return []
    return [
        (tx.pk, f"{tx.external_ref} · {tx.amount} {tx.currency}")
        for tx in transactions_for_leg(leg).order_by("external_ref")[:500]
    ]


@staff_member_required(login_url="ops-login")
def exception_list(request, project_id: int):
    project = get_object_or_404(ReconProject, pk=project_id)
    filters = ExceptionFilterForm(request.GET)
    qs = ExceptionRecord.objects.filter(project=project).select_related(
        "transaction", "run", "resolved_by"
    )
    if filters.is_valid():
        if filters.cleaned_data.get("status"):
            qs = qs.filter(status=filters.cleaned_data["status"])
        if filters.cleaned_data.get("side"):
            qs = qs.filter(side=filters.cleaned_data["side"])
    records = qs.order_by("-created_at")[:500]
    return render(
        request,
        "ops/recon_exceptions.html",
        {
            "project": project,
            "records": records,
            "filter_form": filters,
            "active_count": project.exceptions.filter(
                status__in=[ExceptionRecord.Status.OPEN, ExceptionRecord.Status.INVESTIGATING]
            ).count(),
        },
    )


@staff_member_required(login_url="ops-login")
def exception_detail(request, project_id: int, exception_id: int):
    project = get_object_or_404(ReconProject, pk=project_id)
    record = get_object_or_404(
        ExceptionRecord.objects.select_related("transaction", "run", "resolved_by", "paired_transaction"),
        pk=exception_id,
        project=project,
    )
    manual_form = ResolveManualMatchForm()
    manual_form.fields["counterparty_id"].widget = forms.Select(
        choices=[("", "— select row —")] + _counterparty_choices(project, record)
    )
    similar_cases = []
    try:
        from apps.ai_agent.rag.indexing import exception_query_text
        from apps.ai_agent.tools.tools import retrieve_similar_past_cases

        similar_cases = retrieve_similar_past_cases(
            exception_query_text(record),
            k=5,
            exclude_exception_id=record.pk,
            project_id=project.pk,
        )
    except Exception:
        similar_cases = []
    return render(
        request,
        "ops/recon_exception_detail.html",
        {
            "project": project,
            "record": record,
            "manual_form": manual_form,
            "write_off_form": ResolveWriteOffForm(),
            "reject_form": RejectForm(),
            "similar_cases": similar_cases,
        },
    )


@staff_member_required(login_url="ops-login")
def exception_action(request, project_id: int, exception_id: int):
    if request.method != "POST":
        return redirect("ops-recon-exception-detail", project_id=project_id, exception_id=exception_id)

    project = get_object_or_404(ReconProject, pk=project_id)
    record = get_object_or_404(ExceptionRecord, pk=exception_id, project=project)
    action = (request.POST.get("action") or "").strip()

    try:
        if action == "investigate":
            start_investigating(record, request.user)
            messages.success(request, "Marked as investigating.")
        elif action == "reject":
            form = RejectForm(request.POST)
            if not form.is_valid():
                raise ExceptionWorkflowError("Invalid form.")
            reject_exception(record, request.user, form.cleaned_data.get("note") or "")
            messages.success(request, "Exception rejected.")
        elif action == "write_off":
            form = ResolveWriteOffForm(request.POST)
            if not form.is_valid():
                raise ExceptionWorkflowError("Invalid form.")
            resolve_write_off(record, request.user, form.cleaned_data["note"])
            messages.success(request, "Write-off recorded.")
        elif action == "manual_match":
            form = ResolveManualMatchForm(request.POST)
            if not form.is_valid():
                raise ExceptionWorkflowError("Invalid form.")
            from apps.reconciliation.models import Transaction

            counterparty = get_object_or_404(Transaction, pk=form.cleaned_data["counterparty_id"])
            resolve_manual_match(
                record,
                request.user,
                counterparty,
                form.cleaned_data.get("note") or "",
            )
            messages.success(request, "Manual match saved.")
        else:
            messages.error(request, "Unknown action.")
    except ExceptionWorkflowError as exc:
        messages.error(request, str(exc))

    return redirect("ops-recon-exception-detail", project_id=project_id, exception_id=exception_id)
