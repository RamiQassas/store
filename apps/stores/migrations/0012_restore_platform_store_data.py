from django.db import migrations
from django.db.models import Q

def restore_platform_data(apps, schema_editor):
    try:
        from apps.common.tenant_utils import bypass_tenant_filter
        from apps.providers.models import ProviderProfile
        from apps.catalog.models import Product, Category
        from apps.stores.models import Store

        with bypass_tenant_filter():
            # If no platform profile exists with store=None, restore the first hijacked one
            if not ProviderProfile.all_objects.filter(store__isnull=True).exists():
                hijacked = ProviderProfile.all_objects.filter(
                    Q(base_url__icontains="alkasr") | Q(provider_name__in=["رقميات", "Alkasr VIP", "الكسر VIP", "الكاسر VIP"])
                ).first()
                if hijacked:
                    hijacked.store = None
                    hijacked.save(update_fields=["store"])

            # Check if there are any products created by Alkasr mapper that were attached to a tenant store
            first_store = Store.objects.order_by("created_at", "id").first()
            if first_store and not Product.all_objects.filter(store__isnull=True).exists():
                Product.all_objects.filter(store=first_store, api_provider__in=["alkasr", "tafa3olcard"]).update(store=None)
                Category.all_objects.filter(store=first_store, name__in=[
                    "شحن الألعاب", "شحن التطبيقات", "اتصالات ورصيد", "بطاقات رقمية", 
                    "خدمات التلفزيون والبث", "أرقام وحسابات", "اشتراكات VPN", 
                    "الذكاء الاصطناعي", "برامج وتصميم", "تحويلات مالية", "ترويج ودعم السوشيال ميديا"
                ]).update(store=None)
    except Exception as e:
        print(f"Platform data restore warning: {e}")

def reverse_noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0011_deduplicate_catalogs_data'),
    ]

    operations = [
        migrations.RunPython(restore_platform_data, reverse_noop),
    ]
