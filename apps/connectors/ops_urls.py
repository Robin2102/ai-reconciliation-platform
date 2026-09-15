from django.urls import path

from apps.connectors import ops_views

urlpatterns = [
    path("", ops_views.connector_home, name="ops-connectors"),
    path("new/", ops_views.connector_create, name="ops-connector-create"),
    path("<int:connector_id>/", ops_views.connector_detail, name="ops-connector-detail"),
    path("<int:connector_id>/test/", ops_views.connector_test, name="ops-connector-test"),
    path("<int:connector_id>/browse/", ops_views.connector_browse_api, name="ops-connector-browse-api"),
]
