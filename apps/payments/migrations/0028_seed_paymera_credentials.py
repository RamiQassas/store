# Generated manually for seeding Paymera credentials on deploy

from django.db import migrations


def seed_paymera(apps, schema_editor):
    PaymentGatewayIntegration = apps.get_model('payments', 'PaymentGatewayIntegration')
    PaymentMethod = apps.get_model('payments', 'PaymentMethod')

    # 1. Update or create global gateway
    gw = PaymentGatewayIntegration.objects.filter(provider='paymera', store__isnull=True).first()
    if not gw:
        gw = PaymentGatewayIntegration.objects.create(
            provider='paymera',
            store=None,
            name='Paymera eGate',
            terminal_id='14740429',
            api_key='70504_FSdHLdNbZaa2KC6PthtNSuKqtgc88fiABRGxPczJ',
            base_url='https://egate-t.paymera.cc',
            mode='sandbox',
            is_active=True,
            can_deposit=True,
        )
    else:
        gw.name = 'Paymera eGate'
        gw.terminal_id = '14740429'
        gw.api_key = '70504_FSdHLdNbZaa2KC6PthtNSuKqtgc88fiABRGxPczJ'
        gw.base_url = 'https://egate-t.paymera.cc'
        gw.mode = 'sandbox'
        gw.is_active = True
        gw.can_deposit = True
        gw.save()

    # 2. Update any other Paymera gateways that have empty credentials
    for other_gw in PaymentGatewayIntegration.objects.filter(provider='paymera'):
        if not other_gw.terminal_id or not other_gw.api_key:
            other_gw.terminal_id = '14740429'
            other_gw.api_key = '70504_FSdHLdNbZaa2KC6PthtNSuKqtgc88fiABRGxPczJ'
            other_gw.base_url = 'https://egate-t.paymera.cc'
            other_gw.mode = 'sandbox'
            other_gw.is_active = True
            other_gw.can_deposit = True
            other_gw.save()

    # 3. Ensure payment methods linked to Paymera are active
    for pm in PaymentMethod.objects.filter(gateway__provider='paymera'):
        pm.is_active = True
        pm.can_deposit = True
        pm.save()


def reverse_seed_paymera(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0027_depositrequest_gateway_payment_id_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_paymera, reverse_seed_paymera),
    ]
