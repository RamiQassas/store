from django.core.management.base import BaseCommand
from apps.providers.models import ProviderProfile, ProviderProduct
from apps.providers.alkasr.mapper import AlkasrMapperService
from apps.catalog.models import Product, ProductVariant, Category

class Command(BaseCommand):
    help = 'Remaps Alkasr products into properly grouped and categorized store catalog.'

    def handle(self, *args, **options):
        profiles = ProviderProfile.objects.filter(is_active=True)
        if not profiles.exists():
            self.stdout.write(self.style.WARNING('No active ProviderProfile found.'))
            return

        for profile in profiles:
            self.stdout.write(f'Processing profile: {profile.provider_name} (ID: {profile.id})...')
            
            # Check if sync is needed
            p_count = ProviderProduct.objects.filter(profile=profile).count()
            if p_count == 0:
                self.stdout.write('No ProviderProducts found. Running initial sync from Alkasr...')
                try:
                    from apps.providers.alkasr.sync import AlkasrSyncService
                    sync_svc = AlkasrSyncService(profile)
                    sync_svc.sync_catalog()
                    self.stdout.write(self.style.SUCCESS('Initial sync completed.'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Sync error: {e}'))
            
            mapper = AlkasrMapperService(profile)
            mapper.map_all_to_catalog()
            
            # Also ensure all variants belonging to alkasr products are active
            ProductVariant.objects.filter(product__api_provider='alkasr').update(is_active=True, is_temporarily_disabled=False)
            Product.objects.filter(api_provider='alkasr').update(is_active=True, is_out_of_stock=False)

            total_cats = Category.objects.count()
            total_prods = Product.objects.filter(api_provider='alkasr').count()
            total_vars = ProductVariant.objects.filter(product__api_provider='alkasr').count()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully remapped Alkasr catalog: {total_prods} products, {total_vars} variants across {total_cats} categories.'
            ))
