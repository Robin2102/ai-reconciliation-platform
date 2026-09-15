from django.contrib import admin

from apps.ai_agent.models import KnowledgeChunk


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "exception_id", "project_id", "updated_at")
    search_fields = ("text",)
    readonly_fields = ("embedding", "created_at", "updated_at")
