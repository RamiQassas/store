import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.providers.models import ProviderProfile
from services.provider.alkasr.client import AlkasrClient

def fetch_data():
    profile = ProviderProfile.objects.filter(provider_name="alkasr", is_active=True).first()
    if not profile:
        print("No active Alkasr profile")
        return
        
    client = AlkasrClient(api_token=profile.api_token, base_url=profile.base_url, profile=profile)
    data = client.get_products()
    
    print("Found", len(data), "products")
    
    uc_products = []
    syriatel_products = []
    
    for item in data:
        name = item.get('name', '').lower()
        if 'uc' in name or 'ببجي' in name:
            uc_products.append(item)
        if 'سيريتل' in name or 'syriatel' in name or 'mtn' in name:
            syriatel_products.append(item)
            
    with open('scratch/alkasr_debug.txt', 'w', encoding='utf-8') as f:
        f.write("UC PRODUCTS (first 5):\n")
        f.write(json.dumps(uc_products[:5], ensure_ascii=False, indent=2))
        f.write("\n\nSYRIATEL/MTN PRODUCTS (first 5):\n")
        f.write(json.dumps(syriatel_products[:5], ensure_ascii=False, indent=2))
        
    print("Data written to scratch/alkasr_debug.txt")

if __name__ == "__main__":
    fetch_data()
