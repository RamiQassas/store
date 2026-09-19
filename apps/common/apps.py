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
            is_server = any(srv in cmd_line for srv in ["gunicorn", "daphne", "uvicorn"]) or os.environ.get("RUN_MAIN") == "true" or os.environ.get("ENABLE_AUTO_DEPLOY_POLLER") == "true"
            if not is_server:
                return
            from apps.common.auto_deploy import start_auto_deploy_background_thread
            start_auto_deploy_background_thread()
        except Exception:
            pass
