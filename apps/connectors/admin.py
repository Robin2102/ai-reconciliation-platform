from django.contrib import admin

from apps.connectors.models import Connector, SourceDefinition, SourceFileSpec


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ("name", "connector_type", "is_active", "updated_at")
    list_filter = ("connector_type", "is_active")
    readonly_fields = ("secrets_ciphertext", "created_at", "updated_at")


class SourceFileSpecInline(admin.TabularInline):
    model = SourceFileSpec
    extra = 0


@admin.register(SourceDefinition)
class SourceDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "source_id", "connector", "default_source_type")
    search_fields = ("name", "source_id")
    inlines = (SourceFileSpecInline,)
