"""
Migration 0042: Fix metadata and qty_type on all variants.
Ensures package products are fixed (qty=1) and removes is_per_mille flag.
"""
from django.db import migrations


def fix_variant_qty_types(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    updated = 0
    for v in ProductVariant.objects.all():
        meta = dict(v.metadata or {})
        product_type = meta.get("product_type")
        qty_min = meta.get("qty_min")
        qty_max = meta.get("qty_max")
        qty_list = meta.get("qty_list") or []

        # Remove is_per_mille flag
        if "is_per_mille" in meta:
            meta.pop("is_per_mille", None)

        # If product_type is package or null qty_values, qty_type must be fixed
        if product_type == "package" or (qty_min == 1 and (qty_max == 1 or qty_max is None) and not qty_list):
            meta["qty_type"] = "fixed"
            meta["qty_min"] = 1
            meta["qty_max"] = 1
        elif product_type == "fixed_quantities" or len(qty_list) > 0:
            meta["qty_type"] = "list"
        elif product_type == "amount":
            meta["qty_type"] = "range"

        v.metadata = meta
        v.save(update_fields=["metadata"])
        updated += 1
    print(f"[0042] Updated metadata for {updated} variants.")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0041_auto_sync_after_wipe"),
    ]

    operations = [
        migrations.RunPython(fix_variant_qty_types, noop_reverse),
    ]
