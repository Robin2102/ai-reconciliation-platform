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
    path("", ops_views.ingest_home, name="ops-ingest"),
    path("files/", ops_views.ingest_file_list, name="ops-ingest-files"),
    path("mapping/<int:file_id>/", ops_views.mapping_studio, name="ops-mapping"),
    path("mapping/<int:file_id>/status/", ops_views.mapping_job_status, name="ops-mapping-status"),
    path("results/<int:file_id>/", ops_views.ingest_results, name="ops-ingest-results"),
    path("recon/", include("apps.reconciliation.ops_urls")),
]
