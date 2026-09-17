"""
Management command: python manage.py sync_alkasr

Runs the Alkasr VIP catalog sync for all active provider profiles.
Usage:
    python manage.py sync_alkasr
    python manage.py sync_alkasr --profile-id=1
"""
from django.core.management.base import BaseCommand
from apps.providers.models import ProviderProfile


class Command(BaseCommand):
    help = "Sync Alkasr VIP catalog: import all products/categories from the API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile-id",
            type=int,
            default=None,
            help="Specific ProviderProfile ID to sync (default: all active profiles)",
        )

    def handle(self, *args, **options):
        profile_id = options.get("profile_id")
        from services.provider.manager import ProviderManager

        if profile_id:
            profiles = ProviderProfile.all_objects.filter(id=profile_id, is_active=True)
        else:
            profiles = ProviderProfile.all_objects.filter(is_active=True, store__isnull=True)

        if not profiles.exists():
            self.stderr.write(self.style.ERROR("No active provider profiles found."))
            return

        for profile in profiles:
            self.stdout.write(f"Syncing profile: {profile} (ID={profile.id})...")
            try:
                stats = ProviderManager.sync_catalog(profile)
                self.stdout.write(self.style.SUCCESS(
                    f"  Done: created={stats.get('created',0)}, "
                    f"updated={stats.get('updated',0)}, "
                    f"disabled={stats.get('disabled',0)}"
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  FAILED: {e}"))
