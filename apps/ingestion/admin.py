from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from apps.ingestion.models import RawRecord
from apps.ingestion.tasks import enqueue_ingest_file


class IngestUploadForm(forms.Form):
    file = forms.FileField(help_text="CSV with txn_id, date, credit, debit, description, currency.")
    source_type = forms.CharField(initial="csv", max_length=50)
    source_id = forms.CharField(
        required=False,
        max_length=100,
        help_text="Optional. Defaults to the filename without extension.",
    )


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "source_id", "status", "ingested_at")
    list_filter = ("source_type", "status")
    search_fields = ("source_id",)
    readonly_fields = ("source_type", "source_id", "raw_payload", "ingested_at", "status")
    change_list_template = "admin/ingestion/rawrecord/change_list.html"

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        extra = [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="ingestion_rawrecord_upload",
            ),
        ]
        return extra + super().get_urls()

    def upload_view(self, request):
        form = IngestUploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            uploaded = form.cleaned_data["file"]
            source_type = form.cleaned_data["source_type"]
            source_id = form.cleaned_data.get("source_id") or Path(uploaded.name).stem
            try:
                task = enqueue_ingest_file(source_type, source_id, uploaded)
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    (
                        f"Ingest queued (task_id={task.id}, source_id={source_id}). "
                        "Rows appear after the Celery worker finishes."
                    ),
                )
                return redirect(reverse("admin:ingestion_rawrecord_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Upload source file",
        }
        return render(request, "admin/ingestion/upload.html", context)
