import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_populate_public_uuid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='public_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
