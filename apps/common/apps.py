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
            # Avoid starting poller during short-lived CLI tasks, tests, or migrations
            cmd_line = " ".join(sys.argv).lower()
            skip_terms = ["migrate", "collectstatic", "makemigrations", "pytest", "test", "audit", "createsuperuser", "shell", "-c", "scratch"]
            if any(f" {st}" in f" {cmd_line}" or cmd_line.endswith(st) for st in skip_terms):
                return
            
            from apps.common.auto_deploy import start_auto_deploy_background_thread
            start_auto_deploy_background_thread()
        except Exception:
            pass
