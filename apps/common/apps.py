from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        try:
            import sys
            # Avoid starting poller during manage.py tasks or celery workers
            cmd_line = " ".join(sys.argv)
            if "manage.py" in cmd_line or "celery" in cmd_line:
                return
            from apps.common.auto_deploy import start_auto_deploy_background_thread
            start_auto_deploy_background_thread()
        except Exception:
            pass
