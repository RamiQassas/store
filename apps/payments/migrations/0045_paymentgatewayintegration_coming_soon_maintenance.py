from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0044_normalize_shamcash_https_v4"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentgatewayintegration",
            name="is_coming_soon",
            field=models.BooleanField(default=False, verbose_name="قريباً (إيقاف الشراء والإيداع)"),
        ),
        migrations.AddField(
            model_name="paymentgatewayintegration",
            name="is_maintenance_mode",
            field=models.BooleanField(default=False, verbose_name="قيد الصيانة (إيقاف الشراء والإيداع)"),
        ),
    ]
