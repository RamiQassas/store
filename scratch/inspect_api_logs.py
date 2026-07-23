import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.providers.models import ProviderProfile, ProviderSyncLog, ProviderRequestLog, ProviderResponseLog, ProviderErrorLog
from apps.catalog.models import APIIntegration, APITransaction, Product

print("=== APIIntegrations ===")
for api in APIIntegration.objects.all():
    print(f"ID: {api.id}, Store: {api.store}, Name: {api.name}, BaseURL: {api.base_url}, Active: {api.is_active}, Token: {api.api_token[:6]}...")

print("\n=== ProviderProfiles ===")
for p in ProviderProfile.objects.all():
    print(f"ID: {p.id}, Store: {p.store}, Name: {p.provider_name}, BaseURL: {p.base_url}, Active: {p.is_active}")

print("\n=== Recent Sync Logs ===")
for sync_log in ProviderSyncLog.objects.order_by('-created_at')[:10]:
    print(f"ID: {sync_log.id}, Status: {sync_log.status}, Created: {sync_log.products_created}, Error: {sync_log.error_message}")

print("\n=== Recent Provider Request/Response Logs ===")
for req in ProviderRequestLog.objects.order_by('-created_at')[:10]:
    res = ProviderResponseLog.objects.filter(request_log=req).first()
    status = res.status_code if res else "No Res"
    body = res.body[:200] if res else ""
    print(f"URL: {req.endpoint} | HTTP {status} | Body: {body}")

print("\n=== Recent Provider Error Logs ===")
for err in ProviderErrorLog.objects.order_by('-created_at')[:10]:
    print(f"Code: {err.error_code}, Msg: {err.message}, Trace: {err.traceback}")

print("\n=== Recent APITransactions ===")
for tx in APITransaction.objects.order_by('-created_at')[:10]:
    print(f"Action: {tx.action}, URL: {tx.request_url}, Status: {tx.response_status}, Success: {tx.is_success}, Body: {tx.response_body[:200]}")
