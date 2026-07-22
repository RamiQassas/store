from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0014_currency_store_alter_currency_code_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteMaintenanceMode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deposits_enabled', models.BooleanField(default=True, verbose_name='الإيداعات مفعّلة')),
                ('withdrawals_enabled', models.BooleanField(default=True, verbose_name='السحوبات مفعّلة')),
                ('purchases_enabled', models.BooleanField(default=True, verbose_name='الشراء مفعّل')),
                ('transfers_enabled', models.BooleanField(default=True, verbose_name='التحويلات مفعّلة')),
                ('registrations_enabled', models.BooleanField(default=True, verbose_name='التسجيل مفعّل')),
                ('maintenance_message', models.TextField(
                    blank=True,
                    default='الموقع في وضع الصيانة مؤقتاً. سيعود للعمل قريباً.',
                    verbose_name='رسالة الصيانة'
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maintenance_mode_changes',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='آخر تعديل بواسطة'
                )),
            ],
            options={
                'verbose_name': 'وضع الصيانة',
                'verbose_name_plural': 'وضع الصيانة',
            },
        ),
    ]
