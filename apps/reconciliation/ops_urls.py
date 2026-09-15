from django.urls import path

from apps.exceptions import ops_views as exception_ops_views
from apps.reconciliation import ops_views

urlpatterns = [
    path("", ops_views.recon_home, name="ops-recon"),
    path("<int:project_id>/", ops_views.recon_detail, name="ops-recon-detail"),
    path("<int:project_id>/rules/add/", ops_views.recon_add_rule, name="ops-recon-add-rule"),
    path("<int:project_id>/exceptions/", exception_ops_views.exception_list, name="ops-recon-exceptions"),
    path(
        "<int:project_id>/exceptions/<int:exception_id>/",
        exception_ops_views.exception_detail,
        name="ops-recon-exception-detail",
    ),
    path(
        "<int:project_id>/exceptions/<int:exception_id>/action/",
        exception_ops_views.exception_action,
        name="ops-recon-exception-action",
    ),
    path("<int:project_id>/run/", ops_views.recon_run, name="ops-recon-run"),
]
