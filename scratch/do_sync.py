import os
import django
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.providers.models import ProviderProfile
from apps.providers.alkasr import AlkasrSyncService
from apps.catalog.models import Product, ProductVariant

def clear_and_sync():
    try:
        profile = ProviderProfile.objects.filter(provider_name="alkasr", is_active=True).first()
        if not profile:
            print("Alkasr profile not found or inactive!")
            return

        print("Clearing catalog...")
        # Delete API products mapped to alkasr
        deleted_products = Product.objects.filter(is_api_product=True, api_provider="alkasr", store=profile.store).delete()
        print(f"Deleted products: {deleted_products}")

        print("Starting sync...")
        sync_service = AlkasrSyncService(profile)
        stats = sync_service.sync_products(map_to_catalog=True)
        
        print("\nSync Stats:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

        # Verify counts
        print("\nVerification:")
        total_products = Product.objects.filter(is_api_product=True, api_provider="alkasr").count()
        total_variants = ProductVariant.objects.filter(product__is_api_product=True, product__api_provider="alkasr").count()
        
        print(f"Total grouped products created: {total_products}")
        print(f"Total variants created: {total_variants}")

    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    clear_and_sync()
