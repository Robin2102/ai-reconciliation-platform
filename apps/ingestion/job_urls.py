from django.urls import path

from apps.ingestion import job_mapping_views, job_ops_views

urlpatterns = [
    path("", job_ops_views.job_home, name="ops-jobs"),
    path("new/", job_ops_views.job_create, name="ops-job-create"),
    path("<int:job_id>/", job_ops_views.job_detail, name="ops-job-detail"),
    path("<int:job_id>/mapping/", job_mapping_views.job_mapping, name="ops-job-mapping"),
    path(
        "<int:job_id>/mapping/refresh/",
        job_mapping_views.job_mapping_refresh,
        name="ops-job-mapping-refresh",
    ),
    path("<int:job_id>/files/add/", job_ops_views.job_add_connector_files, name="ops-job-add-files"),
    path("<int:job_id>/run/", job_ops_views.job_run, name="ops-job-run"),
]
