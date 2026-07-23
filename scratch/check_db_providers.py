import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.providers.models import ProviderProfile, ProviderProduct, ProviderCategory, ProviderSyncLog, ProviderErrorLog
from apps.catalog.models import Product, APIIntegration

print("=== APIIntegrations ===")
for api in APIIntegration.objects.all():
    print(f"ID: {api.id}, Store: {api.store}, Name: {api.name}, BaseURL: {api.base_url}, Active: {api.is_active}")

print("\n=== ProviderProfiles ===")
for p in ProviderProfile.objects.all():
    print(f"ID: {p.id}, Store: {p.store}, Name: {p.provider_name}, BaseURL: {p.base_url}, Active: {p.is_active}, Balance: {p.balance}")

print("\n=== ProviderProducts count ===")
print("Total ProviderProducts:", ProviderProduct.objects.count())

print("\n=== Products with is_api_product=True ===")
print("Total API Products:", Product.objects.filter(is_api_product=True).count())

print("\n=== Recent ProviderSyncLog ===")
for log in ProviderSyncLog.objects.order_by('-created_at')[:5]:
    print(f"ID: {log.id}, Status: {log.status}, Created: {log.products_created}, Updated: {log.products_updated}, Disabled: {log.products_disabled}, Error: {log.error_message}")

print("\n=== Recent ProviderErrorLog ===")
for err in ProviderErrorLog.objects.order_by('-created_at')[:5]:
    print(f"ID: {err.id}, Code: {err.error_code}, Msg: {err.message}")
