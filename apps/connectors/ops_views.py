from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.connectors.models import Connector
from apps.connectors.services import browse_connector, test_connector


class LocalDirectoryConnectorForm(forms.ModelForm):
    base_path = forms.CharField(
        label="Base directory (absolute path)",
        help_text="e.g. …/django-monolith/uploads — must be under CONNECTOR_LOCAL_ALLOWLIST in .env.",
    )

    class Meta:
        model = Connector
        fields = ["name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.config:
            self.fields["base_path"].initial = self.instance.config.get("base_path", "")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.connector_type = Connector.ConnectorType.LOCAL_DIRECTORY
        instance.config = {"base_path": self.cleaned_data["base_path"].strip()}
        if commit:
            instance.save()
        return instance


@staff_member_required(login_url="ops-login")
def connector_home(request):
    connectors = Connector.objects.all()[:50]
    return render(request, "ops/connectors_home.html", {"connectors": connectors})


@staff_member_required(login_url="ops-login")
def connector_create(request):
    form = LocalDirectoryConnectorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        connector = form.save(commit=False)
        connector.created_by = request.user
        connector.save()
        messages.success(request, f"Connector “{connector.name}” saved.")
        return redirect("ops-connector-detail", connector_id=connector.pk)
    return render(request, "ops/connector_form.html", {"form": form, "is_create": True})


@staff_member_required(login_url="ops-login")
def connector_detail(request, connector_id: int):
    connector = get_object_or_404(Connector, pk=connector_id)
    form = LocalDirectoryConnectorForm(request.POST or None, instance=connector)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Connector updated.")
        return redirect("ops-connector-detail", connector_id=connector.pk)
    browse_path = (request.GET.get("path") or "").strip()
    browse = None
    browse_error = ""
    if connector.connector_type == Connector.ConnectorType.LOCAL_DIRECTORY:
        try:
            browse = browse_connector(connector, browse_path)
        except Exception as exc:
            browse_error = str(exc)
    return render(
        request,
        "ops/connector_detail.html",
        {
            "connector": connector,
            "form": form,
            "browse": browse,
            "browse_error": browse_error,
            "browse_path": browse_path,
        },
    )


@staff_member_required(login_url="ops-login")
@require_POST
def connector_test(request, connector_id: int):
    connector = get_object_or_404(Connector, pk=connector_id)
    result = test_connector(connector)
    if result.ok:
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)
    return redirect("ops-connector-detail", connector_id=connector.pk)


@staff_member_required(login_url="ops-login")
@require_GET
def connector_browse_api(request, connector_id: int):
    connector = get_object_or_404(Connector, pk=connector_id)
    path = (request.GET.get("path") or "").strip()
    try:
        listing = browse_connector(connector, path)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "path": listing.path,
            "parent_path": listing.parent_path,
            "entries": [
                {
                    "name": e.name,
                    "path": e.path,
                    "type": e.entry_type,
                    "size": e.size,
                    "modified_at": e.modified_at,
                }
                for e in listing.entries
            ],
        }
    )
