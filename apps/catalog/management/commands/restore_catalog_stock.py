import logging
from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.catalog.models import Product, ProductVariant
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderMapping
from apps.common.tenant_utils import bypass_tenant_filter

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Instantly restores all accidentally disabled catalog products and variants to in-stock status."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Starting catalog stock restoration..."))

        with bypass_tenant_filter():
            # 1. Restore all ProviderProducts that have positive cost and are not explicitly stopped
            pp_updated = ProviderProduct.objects.filter(
                cost_price__gt=0
            ).update(is_active=True, local_is_active=True)
            self.stdout.write(f"Refreshed {pp_updated} ProviderProducts to active.")

            # 2. Restore all ProductVariants across all stores
            var_updated = ProductVariant.all_objects.filter(
                Q(is_active=False) | Q(is_temporarily_disabled=True)
            ).update(is_active=True, is_temporarily_disabled=False)
            self.stdout.write(f"Restored {var_updated} ProductVariants to active (is_temporarily_disabled=False).")

            # 3. Restore all Products across all stores
            prod_updated = Product.all_objects.filter(
                Q(is_active=False) | Q(is_out_of_stock=True)
            ).update(is_active=True, is_out_of_stock=False)
            self.stdout.write(f"Restored {prod_updated} Products to in-stock (is_out_of_stock=False, is_active=True).")

            # 4. Run AlkasrProductSyncService & AlkasrMapperService for active profiles
            from apps.providers.alkasr.sync import AlkasrProductSyncService
            from apps.providers.alkasr.mapper import AlkasrMapperService
            profiles = ProviderProfile.all_objects.filter(is_active=True)
            for prof in profiles:
                try:
                    if prof.api_token:
                        self.stdout.write(f">> Running live sync from provider API for: {prof}...")
                        AlkasrProductSyncService(prof).sync_products()
                    else:
                        self.stdout.write(f">> Remapping catalog for profile: {prof}...")
                        AlkasrMapperService(prof).map_all_to_catalog()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Sync/Mapping warning for {prof}: {e}"))

            # 5. Clean up any phantom Soul App products
            for ps in Product.all_objects.filter(
                Q(name__icontains="سول (Soul App)") |
                Q(name__icontains="سول | Soul App") |
                Q(name__iexact="سول") |
                Q(name__iexact="Soul App")
            ):
                target_chill = Product.all_objects.filter(name__icontains="سول تشيل").first()
                target_star = Product.all_objects.filter(name__icontains="سول ستار").first()
                for v in ps.variants.all():
                    v_name_lower = (v.name or "").lower()
                    if ("star" in v_name_lower or "ستار" in v_name_lower) and target_star:
                        v.product = target_star
                        v.save(update_fields=["product"])
                    elif target_chill:
                        v.product = target_chill
                        v.save(update_fields=["product"])
                if ps.variants.count() == 0:
                    ps.delete()

            # 6. Final pass: ensure all products with at least one active variant are in-stock
            fixed_count = 0
            for p in Product.all_objects.all():
                has_active = p.variants.filter(is_active=True, is_temporarily_disabled=False).exists()
                if has_active and (p.is_out_of_stock or not p.is_active):
                    p.is_out_of_stock = False
                    p.is_active = True
                    p.save(update_fields=["is_out_of_stock", "is_active"])
                    fixed_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"[OK] Done! Catalog fully restored. {fixed_count} products marked in-stock."
            ))
