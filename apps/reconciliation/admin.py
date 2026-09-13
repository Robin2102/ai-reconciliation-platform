from django.contrib import admin

from apps.reconciliation.models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_id",
        "external_ref",
        "cr_amount",
        "dr_amount",
        "amount",
        "currency",
        "timestamp",
    )
    list_filter = ("currency", "source_id")
    search_fields = ("source_id", "external_ref", "description")
    readonly_fields = (
        "source_id",
        "external_ref",
        "cr_amount",
        "dr_amount",
        "amount",
        "currency",
        "timestamp",
        "description",
        "raw_payload",
        "created_at",
    )

    def has_add_permission(self, request):
        return False
