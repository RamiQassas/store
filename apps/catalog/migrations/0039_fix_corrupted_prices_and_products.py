from decimal import Decimal
from django.db import migrations


def fix_prices_and_products(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    Category = apps.get_model('catalog', 'Category')

    games_category = Category.objects.filter(name__icontains="ألعاب").first()
    if not games_category:
        games_category = Category.objects.filter(is_active=True).first()

    # 1. Fix Hago variant prices and any astronomical / corrupted variant prices (> $5,000)
    for v in ProductVariant.objects.all():
        needs_save = False
        if v.price and v.price > Decimal("5000.00"):
            if v.price > Decimal("1000000.00"):
                v.price = (v.price / Decimal("1000000.00")).quantize(Decimal("0.01"))
            elif v.price > Decimal("100000.00"):
                v.price = (v.price / Decimal("100000.00")).quantize(Decimal("0.01"))
            elif v.price > Decimal("10000.00"):
                v.price = (v.price / Decimal("10000.00")).quantize(Decimal("0.01"))
            else:
                v.price = (v.price / Decimal("1000.00")).quantize(Decimal("0.01"))
            
            if v.wholesale_price and v.wholesale_price > Decimal("5000.00"):
                v.wholesale_price = v.price
            if v.cost and v.cost > Decimal("5000.00"):
                v.cost = (v.price * Decimal("0.9")).quantize(Decimal("0.01"))
            needs_save = True

        meta = v.metadata or {}
        if meta.get("qty_type") == "fixed" and meta.get("qty_min", 1) and meta.get("qty_max", 1) and int(meta.get("qty_max", 1)) > int(meta.get("qty_min", 1)):
            meta["qty_type"] = "range"
            v.metadata = meta
            needs_save = True

        if needs_save:
            v.save()

    # 2. Fix PUBG Royale Pass (81bcb72f-161c-42d4-8285-0e0eedf426fd)
    try:
        p1 = Product.objects.filter(id="81bcb72f-161c-42d4-8285-0e0eedf426fd").first()
        if p1:
            p1.name = "ببجي موبايل - رويال باس نخبة (PUBG Mobile Royale Pass)"
            if games_category:
                p1.category = games_category
            p1.save(update_fields=['name', 'category'] if games_category else ['name'])
            for v in p1.variants.all():
                m = v.metadata or {}
                m["params"] = [{"name": "playerId", "label": "معرف اللاعب (Player ID)", "required": True, "type": "text"}]
                v.metadata = m
                v.save(update_fields=['metadata'])
    except Exception as e:
        print("Error fixing p1:", e)

    # 3. Fix PUBG Packs (91be3f47-2ddc-4516-ba29-1802b7a71d07)
    try:
        p2 = Product.objects.filter(id="91be3f47-2ddc-4516-ba29-1802b7a71d07").first()
        if p2:
            p2.name = "ببجي موبايل - حزم وعروض خاصة (PUBG Mobile Special Packs)"
            if games_category:
                p2.category = games_category
            p2.save(update_fields=['name', 'category'] if games_category else ['name'])
            for v in p2.variants.all():
                m = v.metadata or {}
                m["params"] = [{"name": "playerId", "label": "معرف اللاعب (Player ID)", "required": True, "type": "text"}]
                v.metadata = m
                v.save(update_fields=['metadata'])
    except Exception as e:
        print("Error fixing p2:", e)

    # 4. Fix Server 2 (38ddc219-efaa-4a49-8463-a02897015a5b)
    try:
        s2 = Product.objects.filter(id="38ddc219-efaa-4a49-8463-a02897015a5b").first()
        if s2:
            if s2.name.strip() in ("سيرفر 2", "سيرفر2", "Server 2"):
                s2.name = "شحن ألعاب مباشر - سيرفر 2 (Instant Games Server 2)"
            if games_category:
                s2.category = games_category
            s2.save()
            for v in s2.variants.all():
                m = v.metadata or {}
                if not m.get("params"):
                    m["params"] = [{"name": "playerId", "label": "معرف اللاعب / الحساب (Player ID)", "required": True, "type": "text"}]
                    v.metadata = m
                    v.save(update_fields=['metadata'])
    except Exception as e:
        print("Error fixing s2:", e)

    # 5. Fix Server 4 (fcfda420-84f5-469c-b53a-e3df02aa0656)
    try:
        s4 = Product.objects.filter(id="fcfda420-84f5-469c-b53a-e3df02aa0656").first()
        if s4:
            if s4.name.strip() in ("سيرفر 4", "سيرفر4", "Server 4"):
                s4.name = "شحن ألعاب مباشر - سيرفر 4 (Instant Games Server 4)"
            if games_category:
                s4.category = games_category
            s4.save()
            for v in s4.variants.all():
                m = v.metadata or {}
                if not m.get("params"):
                    m["params"] = [{"name": "playerId", "label": "معرف اللاعب / الحساب (Player ID)", "required": True, "type": "text"}]
                    v.metadata = m
                    v.save(update_fields=['metadata'])
    except Exception as e:
        print("Error fixing s4:", e)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0038_refine_bilingual_names'),
    ]

    operations = [
        migrations.RunPython(fix_prices_and_products, migrations.RunPython.noop),
    ]
