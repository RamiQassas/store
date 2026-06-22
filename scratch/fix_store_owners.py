import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.common.models import Currency
from apps.stores.models import Store

print("Duplicating global currencies to existing stores...")
global_currencies = Currency.all_objects.filter(store__isnull=True)
print(f"Found {global_currencies.count()} global currencies.")

created_count = 0
for store in Store.objects.all():
    print(f"Processing store: {store.name} (Subdomain: {store.subdomain})")
    for gc in global_currencies:
        # Check if the currency already exists for this store
        if not Currency.all_objects.filter(store=store, code=gc.code).exists():
            print(f"Creating store-specific currency {gc.code} for store {store.name}")
            Currency.objects.create(
                store=store,
                name=gc.name,
                code=gc.code,
                symbol=gc.symbol,
                buy_rate=gc.buy_rate,
                sell_rate=gc.sell_rate,
                capital_rate=gc.capital_rate,
                conversion_method=gc.conversion_method,
                decimal_places=gc.decimal_places,
                display_order=gc.display_order,
                is_active=gc.is_active,
                is_default=gc.is_default
            )
            created_count += 1

print(f"Done. Created {created_count} store-specific currency records.")
