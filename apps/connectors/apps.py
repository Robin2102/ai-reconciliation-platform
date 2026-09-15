from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.connectors"
    label = "connectors"

    def ready(self) -> None:
        from apps.connectors.drivers import local_directory  # noqa: F401 — register driver
