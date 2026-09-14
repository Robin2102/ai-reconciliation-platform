from django.contrib import admin

from apps.ingestion.models import IngestFile, MappingTemplate, RawRecord


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "source_id", "status", "ingested_at")
    list_filter = ("source_type", "status")
    search_fields = ("source_id",)
    readonly_fields = ("source_type", "source_id", "raw_payload", "ingested_at", "status")

    def has_add_permission(self, request):
        return False


@admin.register(MappingTemplate)
class MappingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "source_id", "default_currency", "updated_at")
    search_fields = ("name", "source_id")


@admin.register(IngestFile)
class IngestFileAdmin(admin.ModelAdmin):
    list_display = ("id", "original_name", "source_id", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("original_name", "source_id")
    readonly_fields = (
        "path",
        "original_name",
        "source_type",
        "source_id",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
