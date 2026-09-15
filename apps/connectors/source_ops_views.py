from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.adaptors.registry import list_registered_adapters
from apps.connectors.models import Connector, SourceDefinition, SourceFileSpec
from apps.connectors.services import browse_connector
from apps.ingestion.models import MappingTemplate


class SourceDefinitionForm(forms.ModelForm):
    class Meta:
        model = SourceDefinition
        fields = [
            "source_id",
            "name",
            "description",
            "default_source_type",
            "connector",
            "mapping_template",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_source_type"].choices = [(k, k) for k in list_registered_adapters()]
        self.fields["connector"].queryset = Connector.objects.filter(is_active=True)
        self.fields["mapping_template"].queryset = MappingTemplate.objects.all().order_by("-updated_at")
        self.fields["mapping_template"].required = False


@staff_member_required(login_url="ops-login")
def source_home(request):
    sources = SourceDefinition.objects.select_related("connector").prefetch_related("file_specs")[:50]
    return render(request, "ops/sources_home.html", {"sources": sources})


@staff_member_required(login_url="ops-login")
def source_create(request):
    form = SourceDefinitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        source = form.save()
        messages.success(request, f"Source “{source.name}” created.")
        return redirect("ops-source-detail", source_id=source.pk)
    return render(request, "ops/source_form.html", {"form": form})


@staff_member_required(login_url="ops-login")
def source_detail(request, source_id: int):
    source = get_object_or_404(
        SourceDefinition.objects.select_related("connector", "mapping_template"),
        pk=source_id,
    )
    form = SourceDefinitionForm(request.POST or None, instance=source)
    if request.method == "POST" and request.POST.get("_save_source"):
        if form.is_valid():
            form.save()
            messages.success(request, "Source updated.")
            return redirect("ops-source-detail", source_id=source.pk)
    else:
        form = SourceDefinitionForm(instance=source)

    browse_path = (request.GET.get("path") or "").strip()
    browse = None
    browse_error = ""
    if source.connector_id:
        try:
            browse = browse_connector(source.connector, browse_path)
        except Exception as exc:
            browse_error = str(exc)

    return render(
        request,
        "ops/source_detail.html",
        {
            "source": source,
            "form": form,
            "specs": source.file_specs.all(),
            "browse": browse,
            "browse_error": browse_error,
            "browse_path": browse_path,
        },
    )


@staff_member_required(login_url="ops-login")
@require_POST
def source_add_files(request, source_id: int):
    source = get_object_or_404(SourceDefinition, pk=source_id)
    paths = request.POST.getlist("remote_paths")
    if not paths:
        messages.error(request, "Select at least one file.")
        return redirect("ops-source-detail", source_id=source.pk)
    created = 0
    for path in paths:
        path = (path or "").strip()
        if not path:
            continue
        _, was_created = SourceFileSpec.objects.get_or_create(
            source=source,
            remote_path=path,
            defaults={"filename_hint": path.split("/")[-1]},
        )
        if was_created:
            created += 1
    messages.success(request, f"Added {created} file path(s) to source.")
    return redirect("ops-source-detail", source_id=source.pk)


@staff_member_required(login_url="ops-login")
@require_POST
def source_remove_spec(request, source_id: int, spec_id: int):
    source = get_object_or_404(SourceDefinition, pk=source_id)
    SourceFileSpec.objects.filter(pk=spec_id, source=source).delete()
    messages.info(request, "File removed from source.")
    return redirect("ops-source-detail", source_id=source.pk)
