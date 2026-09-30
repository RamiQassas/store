import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderMapping
from apps.catalog.models import Product, ProductVariant, Category
from services.provider.alkasr.mapper import AlkasrMapperService, STANDARD_MAIN_SECTIONS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remaps Alkasr products into properly grouped and categorized store catalog.'

    def add_arguments(self, parser):
        parser.add_argument('--sync', action='store_true', default=False, help='Sync live catalog from provider API before remapping')
        parser.add_argument('--clear', action='store_true', default=False, help='Clear imported products before remapping')
        parser.add_argument('--brand', action='store_true', default=False, help='Apply smart branding to all products')

    def handle(self, *args, **options):
        do_sync = options.get('sync', False)
        do_clear = options.get('clear', False)
        do_brand = options.get('brand', False)

        if do_clear:
            self.stdout.write(self.style.WARNING('Clearing all previously imported provider products and mappings...'))
            ProviderMapping.objects.filter(provider_product__profile__in=ProviderProfile.all_objects.filter(is_active=True)).delete()
            ProductVariant.objects.filter(product__api_provider='alkasr').delete()
            Product.objects.filter(api_provider='alkasr').delete()
            self.stdout.write(self.style.SUCCESS('Catalog cleared cleanly.'))

        # 1. Ensure Standard Categories
        for name, order in STANDARD_MAIN_SECTIONS:
            cat = Category.objects.filter(name=name, store=None).first()
            if not cat:
                cat = Category.objects.filter(name=name).first()
            if not cat:
                cat = Category.objects.create(
                    name=name,
                    store=None,
                    sort_order=order,
                    is_active=True
                )
            else:
                cat.sort_order = order
                cat.is_active = True
                cat.save(update_fields=["sort_order", "is_active"])

        profiles = ProviderProfile.all_objects.filter(is_active=True)
        if not profiles.exists():
            self.stdout.write(self.style.WARNING('No active ProviderProfile found.'))
            return

        for profile in profiles:
            # Live sync if requested or if no products exist yet for this profile
            if do_sync or not ProviderProduct.objects.filter(profile=profile).exists():
                self.stdout.write(f'Syncing live catalog from provider for {profile.provider_name} (ID: {profile.id})...')
                try:
                    from services.provider.manager import ProviderManager
                    ProviderManager.sync_catalog(profile)
                    self.stdout.write(self.style.SUCCESS('Synced live availability and category tree from Alkasr.'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Sync error: {e}'))

            if not ProviderProduct.objects.filter(profile=profile).exists():
                self.stdout.write(f'Skipping profile with no products: {profile.provider_name} (ID: {profile.id})')
                continue
            
            self.stdout.write(f'Processing profile: {profile.provider_name} (ID: {profile.id})...')

            # Map all products to canonical catalog
            mapper = AlkasrMapperService(profile)
            stats = mapper.map_all_to_catalog()
            self.stdout.write(self.style.SUCCESS(f'Mapping stats: {stats}'))

            # Cleanup corrupted mappings & misassigned variants
            cleanup_stats = AlkasrMapperService.cleanup_corrupted_mappings(profile)
            self.stdout.write(self.style.SUCCESS(f'Cleanup stats: {cleanup_stats}'))

            # Delete auto-created dummy variants with 0 price
            ProductVariant.objects.filter(sku__startswith='AUTO-').delete()

            # Clean empty Alkasr products with no variants
            empty_prods = Product.objects.filter(api_provider='alkasr', variants__isnull=True)
            empty_cnt = empty_prods.count()
            empty_prods.delete()
            if empty_cnt > 0:
                self.stdout.write(f'Cleaned up {empty_cnt} empty products with no variants.')

            # Ensure all products across catalog have fallback schema if missing
            for p in Product.objects.filter(api_provider='alkasr'):
                schema = p.form_schema or {}
                fields = schema.get("fields", [])
                if not fields and getattr(p, "product_type", "digital") != "physical":
                    p.form_schema = {
                        "version": 1,
                        "fields": [
                            {
                                "label": "معرف الحساب / الايدي (Player ID)",
                                "name": "player_id",
                                "type": "text",
                                "required": True,
                                "placeholder": "أدخل معرف الحساب أو الآيدي أو رقم الهاتف..."
                            }
                        ]
                    }
                    p.save(update_fields=['form_schema'])

            # Smart branding
            from apps.catalog.smart_branding import apply_branding_to_product
            branded_count = 0
            target_prods = Product.objects.filter(is_active=True)
            if not do_brand:
                target_prods = target_prods.filter(Q(image='') | Q(image__isnull=True))

            for prod in target_prods:
                try:
                    if apply_branding_to_product(prod, force=do_brand):
                        branded_count += 1
                except Exception as b_err:
                    self.stdout.write(self.style.WARNING(f'Branding error for {prod.name}: {b_err}'))

            if branded_count > 0:
                self.stdout.write(self.style.SUCCESS(f'Successfully applied smart branding to {branded_count} products.'))

            total_cats = Category.objects.count()
            total_prods = Product.objects.filter(api_provider='alkasr').count()
            total_vars = ProductVariant.objects.filter(product__api_provider='alkasr').count()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully remapped Alkasr catalog: {total_prods} products, {total_vars} variants across {total_cats} categories.'
            ))
