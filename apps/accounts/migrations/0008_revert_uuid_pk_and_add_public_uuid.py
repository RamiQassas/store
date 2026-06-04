import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_emailverificationtoken'),
    ]

    operations = [
        # 1. Restore bigint ID
        migrations.AlterField(
            model_name='user',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        # 2. Add public_uuid field
        migrations.AddField(
            model_name='user',
            name='public_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
    ]
