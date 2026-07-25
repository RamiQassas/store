import os
import django
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

try:
    from apps.providers.models import ProviderProduct, ProviderSyncLog
    print(f"Total ProviderProducts: {ProviderProduct.objects.count()}")
    log = ProviderSyncLog.objects.order_by('-created_at').first()
    if log:
        print(f"Last sync status: {log.status}, created: {log.products_created}, updated: {log.products_updated}, disabled: {log.products_disabled}")
        print(f"Error msg: {log.error_message}")
except Exception as e:
    traceback.print_exc()
