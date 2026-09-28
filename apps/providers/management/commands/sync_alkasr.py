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
        parser.add_argument(
            "--cleanup",
            action="store_true",
            default=False,
            help="Run database mapping cleanup to fix misassigned packages",
        )
        parser.add_argument(
            "--reconcile",
            action="store_true",
            default=False,
            help="Run order reconciliation for pending/processing orders",
        )

    def handle(self, *args, **options):
        profile_id = options.get("profile_id")
        do_cleanup = options.get("cleanup")
        do_reconcile = options.get("reconcile")
        from services.provider.manager import ProviderManager

        if profile_id:
            profiles = ProviderProfile.all_objects.filter(id=profile_id, is_active=True)
        else:
            profiles = ProviderProfile.all_objects.filter(is_active=True, store__isnull=True)

        if not profiles.exists():
            self.stderr.write(self.style.ERROR("No active provider profiles found."))
            return

        for profile in profiles:
            self.stdout.write(f"Processing profile: {profile} (ID={profile.id})...")

            if do_cleanup:
                self.stdout.write("  Running package mapping cleanup...")
                cleanup_res = ProviderManager.cleanup_mappings(profile)
                self.stdout.write(self.style.SUCCESS(
                    f"  Cleanup finished: reassigned={cleanup_res.get('reassigned_count', 0)}, "
                    f"deactivated={cleanup_res.get('deactivated_count', 0)}"
                ))

            if do_reconcile:
                self.stdout.write("  Running order reconciliation...")
                rec_res = ProviderManager.reconcile_orders(profile)
                self.stdout.write(self.style.SUCCESS(
                    f"  Reconciliation finished: checked={rec_res.get('checked', 0)}, "
                    f"completed={rec_res.get('completed', 0)}, failed={rec_res.get('failed', 0)}, "
                    f"pending={rec_res.get('pending', 0)}"
                ))

            if not do_cleanup and not do_reconcile:
                try:
                    stats = ProviderManager.sync_catalog(profile)
                    self.stdout.write(self.style.SUCCESS(
                        f"  Done: created={stats.get('created',0)}, "
                        f"updated={stats.get('updated',0)}, "
                        f"disabled={stats.get('disabled',0)}"
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  FAILED: {e}"))
