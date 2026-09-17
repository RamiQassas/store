from django.db import migrations

def refine_rename_all_products(apps, schema_editor):
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
    print(f'Refined bilingual renaming completed: {updated} products updated.')

class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0037_smart_bilingual_renaming'),
    ]

    operations = [
        migrations.RunPython(refine_rename_all_products, migrations.RunPython.noop),
    ]
