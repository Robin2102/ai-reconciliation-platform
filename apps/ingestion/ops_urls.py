from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.ingestion import ops_views

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="ops/login.html"),
        name="ops-login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="ops-logout",
    ),
    path("", ops_views.ops_home, name="ops-home"),
    path("results/<int:file_id>/", ops_views.ingest_results, name="ops-ingest-results"),
    path("recon/", include("apps.reconciliation.ops_urls")),
    path("connectors/", include("apps.connectors.ops_urls")),
    path("sources/", include("apps.connectors.source_urls")),
    path("jobs/", include("apps.ingestion.job_urls")),
]
