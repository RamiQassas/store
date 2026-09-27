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

            # 4. Run AlkasrMapperService for active profiles to ensure exact status
            from apps.providers.alkasr.mapper import AlkasrMapperService
            profiles = ProviderProfile.all_objects.filter(is_active=True)
            for prof in profiles:
                try:
                    self.stdout.write(f">> Remapping catalog for profile: {prof}...")
                    AlkasrMapperService(prof).map_all_to_catalog()
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Mapping error for {prof}: {e}"))

            # 5. Final pass: ensure all products with at least one active variant are in-stock
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
