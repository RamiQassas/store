import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.stores.models import Store

stores = Store.unfiltered.all()
print(f"Total stores: {len(stores)}")
for s in stores:
    print(f"Store: {s.name}")
    print(f"  Subdomain: {s.subdomain}")
    print(f"  Owner: {s.owner.email if s.owner else None}")
    print(f"  Logo: {s.logo}")
    print(f"  Logo URL: {s.logo.url if s.logo else None}")
