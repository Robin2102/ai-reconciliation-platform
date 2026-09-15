from django import template

from apps.ingestion.job_create_state import job_create_browse_href

register = template.Library()


@register.simple_tag(takes_context=True)
def job_browse_url(context, path="", **kwargs):
    request = context["request"]
    return job_create_browse_href(request, path=path, **kwargs)
