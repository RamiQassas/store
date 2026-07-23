import os
import sys

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.catalog.models import Product, ProductVariant, Category
from apps.stores.models import Store

print("=== Checking Products in Database ===")
all_products = Product.objects.all()
print("Total Products:", all_products.count())
print("Active Products:", Product.objects.filter(is_active=True).count())

for p in all_products:
    print(f"Product ID: {p.id}, Name: '{p.name}', Store: {p.store}, Active: {p.is_active}, Category: {p.category}, APIProduct: {p.is_api_product}")
    variants = p.variants.all()
    print(f"   Variants count: {variants.count()}")
    for v in variants:
        print(f"      Variant: '{v.name}', Price: {v.price}, Cost: {v.cost}, Active: {v.is_active}")

print("\n=== Checking Categories in Database ===")
all_cats = Category.objects.all()
print("Total Categories:", all_cats.count())
for c in all_cats:
    print(f"Cat ID: {c.id}, Name: '{c.name}', Store: {c.store}, Active: {c.is_active}")
