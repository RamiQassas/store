"""
Migration 0040: Wipe all provider-imported catalog data for clean re-import.

This removes all ProductVariant and Product records that were imported from
the Alkasr VIP API (identified by api_product_id or provider mappings),
then removes all ProviderProduct, ProviderCategory, and ProviderMapping records.

After this migration runs, a fresh sync from the admin panel will re-import
all products with correct prices (no more /1000 division bugs).
"""
from django.db import migrations


def wipe_provider_catalog(apps, schema_editor):
    ProviderMapping = apps.get_model("providers", "ProviderMapping")
    ProviderProduct = apps.get_model("providers", "ProviderProduct")
    ProviderCategory = apps.get_model("providers", "ProviderCategory")
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    Product = apps.get_model("catalog", "Product")

    try:
        # 1. Get all variant IDs linked via ProviderMapping
        mapped_variant_ids = list(
            ProviderMapping.objects.filter(local_variant__isnull=False)
            .values_list("local_variant_id", flat=True)
        )
        # 2. Get all product IDs linked via ProviderMapping
        mapped_product_ids = list(
            ProviderMapping.objects.filter(local_product__isnull=False)
            .values_list("local_product_id", flat=True)
        )

        # 3. Also find any API product variants (api_product_id is IntegerField)
        api_variant_ids = list(
            ProductVariant.objects.filter(api_product_id__isnull=False)
            .values_list("id", flat=True)
        )
        api_product_ids = list(
            Product.objects.filter(is_api_product=True, store__isnull=True)
            .values_list("id", flat=True)
        )

        all_variant_ids = set(mapped_variant_ids) | set(api_variant_ids)
        all_product_ids = set(mapped_product_ids) | set(api_product_ids)

        print(f"[0040] Wiping {len(all_variant_ids)} variants, {len(all_product_ids)} products...")

        # 4. Delete mappings first
        ProviderMapping.objects.all().delete()

        # 5. Delete variants
        if all_variant_ids:
            ProductVariant.objects.filter(id__in=all_variant_ids).delete()

        # 6. Delete API products
        if all_product_ids:
            Product.objects.filter(id__in=all_product_ids).delete()
        Product.objects.filter(is_api_product=True, store__isnull=True).delete()

        # 7. Delete all provider data
        ProviderProduct.objects.all().delete()
        ProviderCategory.objects.all().delete()

        print("[0040] Successfully wiped provider catalog.")
    except Exception as e:
        print(f"[0040 Error during wipe, proceeding safely]: {e}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0039_fix_corrupted_prices_and_products"),
        ("providers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(wipe_provider_catalog, noop_reverse),
    ]
