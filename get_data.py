import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.providers.models import ProviderProfile
from services.provider.alkasr.client import AlkasrClient
from services.provider.alkasr.products import AlkasrProductService

def main():
    p = ProviderProfile.objects.filter(provider_name__icontains='alkasr', is_active=True).first()
    if not p:
        print("No profile")
        return
    c = AlkasrClient(api_token=p.api_token, base_url=p.base_url, profile=p)
    res = c.get_products()
    s = AlkasrProductService(c)
    parsed = s.parse_products_response(res)
    
    cats = {}
    examples = []
    
    for x in parsed:
        cname = x.get('category_name')
        if cname not in cats: 
            cats[cname] = []
        cats[cname].append(x)
        
        name = x.get('name', '').lower()
        if 'mtn' in name or 'سيريتل' in name or 'رصيد' in name or 'فواتير' in name:
            if len(examples) < 10:
                examples.append(x)
                
    output = {
        "categories": {k: [p['name'] for p in v[:3]] for k, v in cats.items()},
        "mtn_examples": examples
    }
    
    with open('api_dump.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Done writing api_dump.json")

if __name__ == '__main__':
    main()
