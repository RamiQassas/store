from django.db import migrations

def run_deduplicate(apps, schema_editor):
    try:
        from apps.stores.services import deduplicate_all_stores
        deduplicate_all_stores()
    except Exception as e:
        print(f"Catalog deduplication during migration warning: {e}")

def reverse_noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0010_store_tier_margins'),
    ]

    operations = [
        migrations.RunPython(run_deduplicate, reverse_noop),
    ]
