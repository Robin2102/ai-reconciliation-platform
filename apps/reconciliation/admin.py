from django.contrib import admin

from apps.reconciliation.models import Transaction
from apps.reconciliation.recon_models import MatchResult, MatchRule, ReconLeg, ReconProject, ReconRun


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


class ReconLegInline(admin.TabularInline):
    model = ReconLeg
    extra = 0
    readonly_fields = ("feed_key", "row_count")


class MatchRuleInline(admin.TabularInline):
    model = MatchRule
    extra = 0


@admin.register(ReconProject)
class ReconProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name",)
    inlines = (ReconLegInline, MatchRuleInline)


@admin.register(ReconRun)
class ReconRunAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "status", "started_at", "finished_at")
    list_filter = ("status",)
    readonly_fields = ("stats", "error_message", "started_at", "finished_at")


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "rule_name", "confidence", "source_transaction", "target_transaction")
    list_filter = ("rule_name",)
