import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from unittest.mock import MagicMock
from django.core.cache import cache
from apps.providers.models import ProviderProfile
from apps.providers.alkasr import AlkasrSyncService, APIError

print("=== Testing Error Propagation in AlkasrSyncService ===")

profile, _ = ProviderProfile.objects.get_or_create(
    provider_name="TestErrorProvider",
    defaults={
        "base_url": "https://api.alkasr-vip.com/",
        "api_token": "invalid-token",
        "is_active": True
    }
)

sync_svc = AlkasrSyncService(profile)

# Mock fetch_products to simulate API Token Error (Code 120 / 121)
sync_svc.product_svc.fetch_products = MagicMock(side_effect=APIError("Api Token is required! (ERR-120)"))

try:
    sync_svc.sync_catalog()
except APIError as e:
    print("Caught expected APIError:", e)

# Check cached progress
progress = cache.get(f"sync_progress_{profile.id}")
print("\nCached Progress status on error:")
print(progress)

assert progress["status"] == "failed"
assert "120" in progress["error"] or "Token" in progress["error"]
print("\nVerification Passed: Errors are now properly reported to cache and UI progress bar!")

profile.delete()
