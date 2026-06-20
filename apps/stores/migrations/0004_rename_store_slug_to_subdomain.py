from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0003_store_button_color_store_card_style_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='store',
            old_name='slug',
            new_name='subdomain',
        ),
        migrations.AlterField(
            model_name='store',
            name='subdomain',
            field=models.SlugField(max_length=100, unique=True, verbose_name='رابط المتجر الفرعي (Subdomain)'),
        ),
    ]
