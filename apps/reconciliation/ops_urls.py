from django.urls import path

from apps.reconciliation import ops_views

urlpatterns = [
    path("", ops_views.recon_home, name="ops-recon"),
    path("<int:project_id>/", ops_views.recon_detail, name="ops-recon-detail"),
    path("<int:project_id>/rules/add/", ops_views.recon_add_rule, name="ops-recon-add-rule"),
    path("<int:project_id>/exceptions/", ops_views.recon_exceptions, name="ops-recon-exceptions"),
    path("<int:project_id>/run/", ops_views.recon_run, name="ops-recon-run"),
]
