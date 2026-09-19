from django.db import migrations

def set_default_pixel(apps, schema_editor):
    MetaPixelConfiguration = apps.get_model('common', 'MetaPixelConfiguration')
    obj, created = MetaPixelConfiguration.objects.get_or_create(
        store=None,
        defaults={
            'pixel_name': 'بيكسل متجر رقميات الأساسي',
            'pixel_id': '2160585431194060',
            'is_active': True,
            'track_pageviews': True,
            'track_view_content': True,
            'track_initiate_checkout': True,
            'track_purchases': True,
            'track_registrations': True,
        }
    )
    if not created:
        obj.pixel_id = '2160585431194060'
        obj.pixel_name = 'بيكسل متجر رقميات الأساسي'
        obj.is_active = True
        obj.save()

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0018_metapixelconfiguration'),
    ]

    operations = [
        migrations.RunPython(set_default_pixel, migrations.RunPython.noop),
    ]
