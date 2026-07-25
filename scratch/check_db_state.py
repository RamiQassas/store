import os
import sys
import django

sys.path.insert(0, r"C:\Users\a0947\Documents\store")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
django.setup()

from apps.catalog.models import APIIntegration, Product, ProductVariant
from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory

print("=== Checking DB Integrations and Provider Profiles ===")
integrations = APIIntegration.objects.all()
print(f"APIIntegrations count: {integrations.count()}")
for i in integrations:
    print(f"  Integration: id={i.id}, name={i.name}, provider={i.provider}, base_url={i.base_url}, is_active={i.is_active}")

profiles = ProviderProfile.objects.all()
print(f"ProviderProfiles count: {profiles.count()}")
for p in profiles:
    p_prods = ProviderProduct.objects.filter(profile=p)
    p_cats = ProviderCategory.objects.filter(profile=p)
    print(f"  Profile: id={p.id}, name={p.provider_name}, store={p.store}, products_count={p_prods.count()}, categories_count={p_cats.count()}")

local_prods = Product.objects.filter(is_api_product=True)
print(f"Local Store API Products count: {local_prods.count()}")
for lp in local_prods:
    print(f"  Catalog Product: id={lp.id}, name={lp.name}, variants={lp.variants.count()}")
