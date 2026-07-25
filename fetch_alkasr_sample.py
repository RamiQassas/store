import os
import django
import json
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

try:
    from apps.providers.models import ProviderProfile
    from services.provider.alkasr.products import AlkasrProductService
    from services.provider.alkasr.client import AlkasrClient

    profile = ProviderProfile.objects.filter(provider_name__icontains='alkasr', is_active=True).first()
    if not profile:
        profile = ProviderProfile.objects.first()

    if profile:
        client = AlkasrClient(api_token=profile.api_token, base_url=profile.base_url, profile=profile)
        service = AlkasrProductService(client)
        raw_data = client.get_products()
        
        parsed = service.parse_products_response(raw_data)
        
        print(f"Fetched {len(parsed)} products.")
        
        # Dump a few examples
        examples = []
        for p in parsed:
            name = p.get('name', '').lower()
            if 'pubg' in name or 'ببجي' in name or 'mtn' in name or 'سيريتل' in name or 'رصيد' in name or 'فواتير' in name:
                examples.append(p)
            if len(examples) > 10:
                break
                
        if not examples and parsed:
            examples = parsed[:5]
            
        with open('alkasr_sample.json', 'w', encoding='utf-8') as f:
            json.dump(examples, f, ensure_ascii=False, indent=2)
        print("Wrote sample to alkasr_sample.json")
    else:
        print("No active ProviderProfile found.")

except Exception as e:
    traceback.print_exc()
