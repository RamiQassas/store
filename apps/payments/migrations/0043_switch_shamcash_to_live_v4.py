import os
from django.db import migrations


OLD_SANDBOX_AGENT_KEY = "LELCNDrzTrEgXtv00OUdVeECa1CEZZiC"
OLD_SANDBOX_SECRET_KEY = "1ZogpKWJe6+dv0fey6JjkvigrdLdnq697b4Sl8XeBEg="
OFFICIAL_LIVE_BASE_URL = "https://payment.shamcash.sy/v4"


def switch_shamcash_to_live_v4(apps, schema_editor):
    PaymentGatewayIntegration = apps.get_model("payments", "PaymentGatewayIntegration")
    env_agent = (os.environ.get("SHAM_CASH_AGENT_KEY") or "").strip()
    env_secret = (os.environ.get("SHAM_CASH_SECRET_KEY") or "").strip()
    if env_agent == OLD_SANDBOX_AGENT_KEY:
        env_agent = ""
    if env_secret == OLD_SANDBOX_SECRET_KEY:
        env_secret = ""

    qs = PaymentGatewayIntegration.objects.filter(provider="sham_cash")
    for gw in qs:
        gw.mode = "live"
        curr_url = (gw.base_url or "").strip()
        if not curr_url or "shamlogix" in curr_url.lower() or "api.shamcash.sy" in curr_url.lower():
            gw.base_url = OFFICIAL_LIVE_BASE_URL

        if (gw.api_key or "").strip() == OLD_SANDBOX_AGENT_KEY:
            gw.api_key = ""
        if (gw.api_secret or "").strip() == OLD_SANDBOX_SECRET_KEY:
            gw.api_secret = ""

        if env_agent and not gw.api_key:
            gw.api_key = env_agent
        if env_secret and not gw.api_secret:
            gw.api_secret = env_secret

        if isinstance(gw.settings, dict):
            cleaned_settings = dict(gw.settings)
            cleaned_settings.pop("agent_key", None)
            cleaned_settings.pop("secret_key", None)
            gw.settings = cleaned_settings

        gw.save()


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0042_paymentmethod_is_unlimited_and_more"),
    ]

    operations = [
        migrations.RunPython(switch_shamcash_to_live_v4, migrations.RunPython.noop),
    ]
