from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        try:
            from apps.common.auto_deploy import start_auto_deploy_background_thread
            start_auto_deploy_background_thread()
        except Exception:
            pass
