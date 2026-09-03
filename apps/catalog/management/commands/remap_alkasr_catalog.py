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
            
            # Sync from Alkasr to get latest availability
            try:
                from apps.providers.alkasr.sync import AlkasrSyncService
                sync_svc = AlkasrSyncService(profile)
                sync_svc.sync_catalog()
                self.stdout.write(self.style.SUCCESS('Synced live availability from Alkasr.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Sync error: {e}'))

            mapper = AlkasrMapperService(profile)
            mapper.map_all_to_catalog()
            
            # Clean up empty Alkasr products that have 0 variants
            empty_prods = Product.objects.filter(api_provider='alkasr', variants__isnull=True)
            empty_count = empty_prods.count()
            empty_prods.delete()
            if empty_count > 0:
                self.stdout.write(f'Cleaned up {empty_count} unused empty products.')

            # Deactivate variants linked to inactive or unavailable provider products
            inactive_remote_ids = list(ProviderProduct.objects.filter(profile=profile, is_active=False).values_list('remote_id', flat=True))
            if inactive_remote_ids:
                deactivated = ProductVariant.objects.filter(api_product_id__in=inactive_remote_ids).update(is_active=False, is_temporarily_disabled=True)
                self.stdout.write(f'Deactivated {deactivated} variants because they are unavailable/disabled at provider.')

            # Also deactivate any corrupted fallback variants with (#ID) or null
            bad_vars = ProductVariant.objects.filter(name__icontains='(#').update(is_active=False, is_temporarily_disabled=True)
            if bad_vars:
                self.stdout.write(f'Deactivated {bad_vars} un-named/corrupted fallback variants.')

            total_cats = Category.objects.count()
            total_prods = Product.objects.filter(api_provider='alkasr').count()
            total_vars = ProductVariant.objects.filter(product__api_provider='alkasr').count()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully remapped Alkasr catalog: {total_prods} products, {total_vars} variants across {total_cats} categories.'
            ))
