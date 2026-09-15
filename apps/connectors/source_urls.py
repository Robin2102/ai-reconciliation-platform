from django.shortcuts import redirect
from django.urls import reverse
from django.urls import path


def sources_removed(request):
    return redirect(f"{reverse('ops-job-create')}?fresh=1")


urlpatterns = [
    path("", sources_removed),
    path("<path:rest>", sources_removed),
]
