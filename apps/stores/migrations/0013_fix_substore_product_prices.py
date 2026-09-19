from decimal import Decimal
from django.db import migrations


def safe_quantize(val):
    if val is None or val <= Decimal("0"):
        return Decimal("0.00")
    if val < Decimal("0.01"):
        return val.quantize(Decimal("0.00000001"))
    elif val < Decimal("1.00"):
        return val.quantize(Decimal("0.0001"))
    else:
        return val.quantize(Decimal("0.01"))


def fix_substore_product_prices(apps, schema_editor):
    try:
        from apps.common.tenant_utils import bypass_tenant_filter
        from apps.catalog.models import ProductVariant, Product
        from apps.stores.models import Store

        with bypass_tenant_filter():
            for store in Store.objects.all():
                tier_margins = getattr(store, "tier_margins", {}) or {}
                try:
                    cust_m = Decimal(str(tier_margins.get("customer", 15.0) if tier_margins.get("customer") is not None else 15.0))
                except Exception:
                    cust_m = Decimal("15.0")
                try:
                    deal_m = Decimal(str(tier_margins.get("dealer", 10.0) if tier_margins.get("dealer") is not None else 10.0))
                except Exception:
                    deal_m = Decimal("10.0")
                try:
                    vip_m = Decimal(str(tier_margins.get("vip", 5.0) if tier_margins.get("vip") is not None else 5.0))
                except Exception:
                    vip_m = Decimal("5.0")

                store_vars = ProductVariant.objects.filter(product__store=store)
                for s_var in store_vars:
                    # Find matching global variant
                    g_var = None
                    if s_var.api_product_id:
                        g_var = ProductVariant.objects.filter(
                            product__store__isnull=True,
                            api_product_id=s_var.api_product_id
                        ).first()

                    if not g_var:
                        g_var = ProductVariant.objects.filter(
                            product__store__isnull=True,
                            product__name=s_var.product.name,
                            name=s_var.name
                        ).first()

                    if not g_var and s_var.sku:
                        # Try stripping the store suffix e.g. "-sub" or "-123456"
                        base_sku = s_var.sku.rsplit("-", 1)[0]
                        g_var = ProductVariant.objects.filter(
                            product__store__isnull=True,
                            sku=base_sku
                        ).first()

                    if g_var:
                        effective_base_cost = Decimal("0")
                        if g_var.wholesale_price and g_var.wholesale_price > Decimal("0"):
                            effective_base_cost = g_var.wholesale_price
                        elif g_var.cost and g_var.cost > Decimal("0"):
                            effective_base_cost = g_var.cost
                        elif g_var.price and g_var.price > Decimal("0"):
                            effective_base_cost = g_var.price

                        calc_price = safe_quantize(effective_base_cost * (Decimal("1") + cust_m / Decimal("100"))) if effective_base_cost > Decimal("0") else (g_var.price or Decimal("0"))
                        calc_wholesale = safe_quantize(effective_base_cost * (Decimal("1") + deal_m / Decimal("100"))) if effective_base_cost > Decimal("0") else (g_var.wholesale_price or g_var.price or Decimal("0"))
                        calc_vip = safe_quantize(effective_base_cost * (Decimal("1") + vip_m / Decimal("100"))) if effective_base_cost > Decimal("0") else (g_var.vip_price or g_var.price or Decimal("0"))

                        # Cascade fallbacks
                        final_price = calc_price if calc_price > Decimal("0") else (g_var.price or effective_base_cost)
                        final_wholesale = calc_wholesale if calc_wholesale > Decimal("0") else (g_var.wholesale_price or final_price)
                        final_vip = calc_vip if calc_vip > Decimal("0") else (g_var.vip_price or final_price)

                        fields = []
                        if s_var.price <= Decimal("0") or (s_var.price != final_price and s_var.cost <= Decimal("0")):
                            s_var.price = final_price
                            fields.append("price")

                        if s_var.wholesale_price <= Decimal("0"):
                            s_var.wholesale_price = final_wholesale
                            fields.append("wholesale_price")

                        if s_var.vip_price <= Decimal("0"):
                            s_var.vip_price = final_vip
                            fields.append("vip_price")

                        store_cost = effective_base_cost if effective_base_cost > Decimal("0") else (g_var.cost or Decimal("0"))
                        if s_var.cost <= Decimal("0") and store_cost > Decimal("0"):
                            s_var.cost = store_cost
                            fields.append("cost")

                        if g_var.metadata:
                            merged = dict(s_var.metadata or {})
                            merged.update(g_var.metadata)
                            s_var.metadata = merged
                            fields.append("metadata")

                        if fields:
                            s_var.save(update_fields=fields)
    except Exception as e:
        print(f"Error repairing substore prices: {e}")


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0012_restore_platform_store_data'),
    ]

    operations = [
        migrations.RunPython(fix_substore_product_prices, reverse_noop),
    ]
