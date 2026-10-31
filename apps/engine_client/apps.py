"""Engine client app configuration."""

from django.apps import AppConfig


class EngineClientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.engine_client"
    label = "engine_client"
