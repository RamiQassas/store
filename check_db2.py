import os
import django
import traceback

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    django.setup()

    from apps.providers.models import ProviderProduct, ProviderSyncLog
    from django.db.models import Count

    with open(r'C:\Users\a0947\Documents\store\db_output.txt', 'w', encoding='utf-8') as f:
        f.write(f"Total ProviderProducts: {ProviderProduct.objects.count()}\n")
        f.write(f"Active ProviderProducts: {ProviderProduct.objects.filter(is_active=True).count()}\n")
        
        log = ProviderSyncLog.objects.order_by('-created_at').first()
        if log:
            f.write(f"Last sync status: {log.status}, created: {log.products_created}, updated: {log.products_updated}, disabled: {log.products_disabled}\n")
            f.write(f"Error msg: {log.error_message}\n")
except Exception as e:
    with open(r'C:\Users\a0947\Documents\store\db_output.txt', 'w', encoding='utf-8') as f:
        f.write("ERROR:\n")
        traceback.print_exc(file=f)
