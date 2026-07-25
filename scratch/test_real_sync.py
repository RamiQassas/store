import os
import sys
import django

sys.path.insert(0, r"C:\Users\a0947\Documents\store")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
django.setup()

from apps.catalog.models import APIIntegration, Product, ProductVariant
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory
from services.provider.manager import ProviderManager

print("=== Creating Default APIIntegration & ProviderProfile ===")
integ, created = APIIntegration.objects.get_or_create(
    provider="alkasr",
    defaults={
        "name": "Alkasr VIP",
        "base_url": "https://api.alkasr-vip.com/client/api",
        "api_token": "test_token",
        "is_active": True
    }
)
print(f"APIIntegration: id={integ.id}, name={integ.name}, created={created}")

profile, p_created = ProviderProfile.objects.get_or_create(
    provider_name=integ.name,
    defaults={
        "base_url": integ.base_url,
        "api_token": integ.api_token,
        "is_active": True
    }
)
print(f"ProviderProfile: id={profile.id}, name={profile.provider_name}, p_created={p_created}")

print("\n=== Testing ProviderManager.sync_catalog ===")
try:
    res = ProviderManager.sync_catalog(profile)
    print(f"Sync result: {res}")
except Exception as e:
    print(f"Sync Exception caught: {e}")

print(f"\nProviderProduct Count: {ProviderProduct.objects.filter(profile=profile).count()}")
print(f"ProviderCategory Count: {ProviderCategory.objects.filter(profile=profile).count()}")
print(f"Store Catalog Products (is_api_product=True) Count: {Product.objects.filter(is_api_product=True).count()}")
print(f"Store Catalog ProductVariants Count: {ProductVariant.objects.filter(product__is_api_product=True).count()}")
