from django.apps import AppConfig


class AdaptorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.adaptors"
    label = "adaptors"

    def ready(self):
        # Import concrete adapters so @register_adapter runs at startup.
        from . import csv_adapter  # noqa: F401
        from . import txt_adapter  # noqa: F401
