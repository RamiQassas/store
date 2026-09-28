from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        try:
            from django.conf import settings
            if not settings.AUTO_DEPLOY_ENABLED:
                return
            import sys
            import os
            # Avoid starting poller during manage.py tasks, tests, audits, or celery workers
            cmd_line = " ".join(sys.argv).lower()
            if any(term in cmd_line for term in ["manage.py", "celery", "test", "audit", "pytest", "-c", "scratch"]):
                return
            # Only run background poller if explicitly enabled via environment variable
            if os.environ.get("ENABLE_AUTO_DEPLOY_POLLER", "").lower() != "true":
                return
            from apps.common.auto_deploy import start_auto_deploy_background_thread
            start_auto_deploy_background_thread()
        except Exception:
            pass
