import uuid
from django.db import migrations


def gen_uuid(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.all():
        user.public_uuid = uuid.uuid4()
        user.save(update_fields=['public_uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_revert_uuid_pk_and_add_public_uuid'),
    ]

    operations = [
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
    ]
