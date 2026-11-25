from django.db import migrations


def normalize_shamcash_base_urls(apps, schema_editor):
    """
    Ensures any ShamCash PaymentGatewayIntegration rows that had 'http://payment.shamcash.sy/v4'
    (saved by Django URLField when scheme was omitted) or missing '/v4' are upgraded to
    'https://payment.shamcash.sy/v4' (fixes port-80 HTTP blackhole timeout).
    """
    from apps.payments.shamcash import ShamCashClient

    PaymentGatewayIntegration = apps.get_model("payments", "PaymentGatewayIntegration")
    for gw in PaymentGatewayIntegration.objects.filter(provider="sham_cash"):
        mode = (gw.mode or "live").strip().lower()
        normalized = ShamCashClient.normalize_base_url(gw.base_url, mode=mode)
        if gw.base_url != normalized:
            gw.base_url = normalized
            gw.save(update_fields=["base_url"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0043_switch_shamcash_to_live_v4"),
    ]

    operations = [
        migrations.RunPython(normalize_shamcash_base_urls, migrations.RunPython.noop),
    ]
