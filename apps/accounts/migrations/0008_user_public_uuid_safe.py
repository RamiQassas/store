import uuid
from django.db import migrations, models

def gen_uuid(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.all():
        user.public_uuid = uuid.uuid4()
        user.save(update_fields=['public_uuid'])

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_emailverificationtoken'),
    ]

    operations = [
        # 1. Add field as nullable
        migrations.AddField(
            model_name='user',
            name='public_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        # 2. Backfill values
        migrations.RunPython(gen_uuid, reverse_code=migrations.RunPython.noop),
        # 3. Enforce unique and non-null
        migrations.AlterField(
            model_name='user',
            name='public_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
