import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.providers.models import ProviderProduct
from django.db.models.deletion import Collector

qs = ProviderProduct.objects.all()
print("Queryset count:", qs.count())

if qs.count() > 0:
    collector = Collector(using='default')
    collector.collect(qs)
    print("Collected classes:", collector.data.keys())
