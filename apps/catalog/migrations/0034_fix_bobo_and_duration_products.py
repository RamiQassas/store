import re
from decimal import Decimal
from django.db import migrations

def fix_catalog_products(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    Category = apps.get_model('catalog', 'Category')

    app_cat = Category.objects.filter(name='شحن التطبيقات').first()
    if not app_cat:
        app_cat = Category.objects.filter(name__icontains='تطبيقات').first()

    # 1. Fix products mistakenly named pure durations like '3 شهور'
    duration_regex = r'^[0-9]+\s*(شهر|شهور|سنة|سنوات|أيام|يوم)'
    for p in Product.objects.filter(name__iregex=duration_regex):
        p.name = 'سناب شات بلس (Snapchat Plus)'
        if app_cat:
            p.category = app_cat
        p.save()
        for idx, v in enumerate(p.variants.all(), start=1):
            v.name = f'اشتراك 3 شهور (سيرفر {idx})'
            v.save()

    # 2. Fix Bobo Chat product and variants specifically if price is 0
    bobo_unit_price = Decimal('0.00004806')
    bobo_cost = Decimal('0.00004577')
    for v in ProductVariant.objects.filter(name__icontains='Bobo'):
        if v.price <= 0:
            v.price = bobo_unit_price
            v.cost = bobo_cost
            v.wholesale_price = bobo_unit_price
            v.vip_price = bobo_unit_price
            v.save()

def reverse_fix(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0033_alter_apiintegration_provider_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_catalog_products, reverse_fix),
    ]
