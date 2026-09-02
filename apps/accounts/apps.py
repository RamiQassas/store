import os
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        import apps.accounts.signals  # noqa: F401
        post_migrate.connect(sync_google_social_app_signal, sender=self)


def sync_google_social_app_signal(sender, **kwargs):
    try:
        from django.conf import settings
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "") or os.environ.get("GOOGLE_CLIENT_ID", "")
        secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "") or os.environ.get("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not secret:
            return

        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        app, created = SocialApp.objects.get_or_create(
            provider="google",
            defaults={
                "name": "Google",
                "client_id": client_id,
                "secret": secret,
            }
        )
        if not created and (app.client_id != client_id or app.secret != secret):
            app.client_id = client_id
            app.secret = secret
            app.save()

        site = Site.objects.filter(id=getattr(settings, "SITE_ID", 1)).first()
        if site and site not in app.sites.all():
            app.sites.add(site)
    except Exception:
        pass
