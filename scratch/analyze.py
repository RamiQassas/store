import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.catalog.models import Product, ProductVariant
from apps.providers.models import ProviderProduct, ProviderProfile

def analyze():
    # 1. Let's see all PUBG products from the provider
    print("Provider Products for PUBG:")
    for pp in ProviderProduct.objects.filter(name__icontains='ببجي')[:20]:
        print(f"ID: {pp.id}, Name: {pp.name}, Type: {pp.product_type}, Qty: {pp.qty_min}-{pp.qty_max}, Parent: {pp.category.parent.name if pp.category and pp.category.parent else 'None'}, Cat: {pp.category.name if pp.category else 'None'}")
        
    print("\nProvider Products for UC:")
    for pp in ProviderProduct.objects.filter(name__icontains='UC ')[:20]:
        print(f"ID: {pp.id}, Name: {pp.name}, Type: {pp.product_type}, Qty: {pp.qty_min}-{pp.qty_max}, Parent: {pp.category.parent.name if pp.category and pp.category.parent else 'None'}, Cat: {pp.category.name if pp.category else 'None'}, Remote_ID: {pp.remote_id}, Parent_ID: {pp.category.parent_remote_id if pp.category else 'None'}")

    print("\nLocal Products in Catalog (babbji):")
    for p in Product.objects.filter(name__icontains='ببجي')[:20]:
        print(f"Product: {p.name}")
        for v in p.variants.all():
            print(f"  Variant: {v.name}, Price: {v.price}, Meta: {v.metadata}")
            
    print("\nLocal Products in Catalog (UC):")
    for p in Product.objects.filter(name__icontains='UC')[:20]:
        print(f"Product: {p.name}")
        for v in p.variants.all():
            print(f"  Variant: {v.name}, Price: {v.price}, Meta: {v.metadata}")

if __name__ == "__main__":
    analyze()
