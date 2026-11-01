from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        try:
            from django.conf import settings
            if not getattr(settings, "AUTO_DEPLOY_ENABLED", True):
                return
            import sys
            import os
            # Avoid starting poller during manage.py tasks, tests, audits, or celery workers
            cmd_line = " ".join(sys.argv).lower()
            if any(term in cmd_line for term in ["manage.py", "celery", "test", "audit", "pytest", "-c", "scratch"]):
                return
            
            from apps.common.auto_deploy import is_auto_deploy_enabled, start_auto_deploy_background_thread
            if is_auto_deploy_enabled():
                start_auto_deploy_background_thread()
        except Exception:
            pass
