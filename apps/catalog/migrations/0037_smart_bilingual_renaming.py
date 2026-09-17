from django.db import migrations

def smart_rename_all_products(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    from apps.catalog.naming import format_bilingual_name
    
    updated = 0
    for product in Product.objects.all():
        old_name = product.name or ''
        new_name = format_bilingual_name(old_name)
        if new_name and new_name != old_name:
            product.name = new_name
            product.save(update_fields=['name'])
            updated += 1
    print(f'Smart bilingual renaming completed: {updated} products updated.')

class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0036_enrich_catalog_bilingual_and_logos'),
    ]

    operations = [
        migrations.RunPython(smart_rename_all_products, migrations.RunPython.noop),
    ]
