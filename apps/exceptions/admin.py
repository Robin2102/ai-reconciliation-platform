from django.contrib import admin

from apps.exceptions.models import ExceptionRecord


@admin.register(ExceptionRecord)
class ExceptionRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "side", "status", "reason", "transaction", "run", "created_at")
    list_filter = ("status", "side", "reason")
    search_fields = ("transaction__external_ref",)
    readonly_fields = ("created_at", "updated_at")
