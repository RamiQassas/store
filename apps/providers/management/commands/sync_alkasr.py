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
            type=str,
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
        parser.add_argument(
            "--reset-catalog",
            action="store_true",
            default=False,
            help="Safely wipe out legacy messy Alkasr products and re-map all catalog items cleanly",
        )
        parser.add_argument(
            "--re-map",
            action="store_true",
            default=False,
            help="Re-map existing ProviderProducts into standard 10 sections without API fetch",
        )

    def handle(self, *args, **options):
        profile_id = options.get("profile_id")
        do_cleanup = options.get("cleanup")
        do_reconcile = options.get("reconcile")
        do_reset = options.get("reset_catalog")
        do_remap = options.get("re_map")
        from services.provider.manager import ProviderManager
        from services.provider.alkasr.mapper import AlkasrMapperService, STANDARD_MAIN_SECTIONS
        from apps.catalog.models import Product, ProductVariant, Category

        if profile_id:
            profiles = ProviderProfile.all_objects.filter(id=profile_id, is_active=True)
        else:
            profiles = ProviderProfile.all_objects.filter(is_active=True)

        if not profiles.exists():
            self.stderr.write(self.style.ERROR("No active provider profiles found."))
            return

        for profile in profiles:
            self.stdout.write(f"Processing profile: {profile} (ID={profile.id})...")

            if do_reset:
                self.stdout.write("  Resetting legacy catalog items for provider 'alkasr'...")
                # Delete Alkasr variants and products
                v_del, _ = ProductVariant.objects.filter(sku__startswith=f"PRV-{profile.id}-").delete()
                p_del, _ = Product.objects.filter(api_provider="alkasr").delete()
                # Clean empty non-standard categories
                std_names = [name for name, _ in STANDARD_MAIN_SECTIONS]
                c_del, _ = Category.objects.filter(products__isnull=True).exclude(name__in=std_names).delete()
                self.stdout.write(self.style.SUCCESS(
                    f"  Reset done: deleted {p_del} products, {v_del} variants, {c_del} empty categories."
                ))
                # Now re-map
                mapper = AlkasrMapperService(profile)
                stats = mapper.map_all_to_catalog()
                self.stdout.write(self.style.SUCCESS(f"  Re-mapped into 10 sections: {stats}"))
                continue

            if do_remap:
                self.stdout.write("  Re-mapping existing provider products into standard sections...")
                mapper = AlkasrMapperService(profile)
                stats = mapper.map_all_to_catalog()
                self.stdout.write(self.style.SUCCESS(f"  Re-mapping finished: {stats}"))
                continue

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

            if not do_cleanup and not do_reconcile and not do_reset and not do_remap:
                try:
                    stats = ProviderManager.sync_catalog(profile)
                    self.stdout.write(self.style.SUCCESS(
                        f"  Done: created={stats.get('created',0)}, "
                        f"updated={stats.get('updated',0)}, "
                        f"disabled={stats.get('disabled',0)}"
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  FAILED: {e}"))
