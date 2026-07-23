import os
import sys

sys.path.insert(0, os.path.abspath('.'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.providers.models import ProviderProfile, ProviderProduct
from apps.catalog.models import Product

ProviderProfile.objects.filter(provider_name="TestProvider").delete()
Product.objects.filter(name__in=["اختبار مجوهرات كلاش اوف كلانس 500", "متابعين انستغرام 1000"]).delete()

print("Test data cleaned up successfully.")
