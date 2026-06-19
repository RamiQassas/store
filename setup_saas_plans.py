import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.stores.models import SubscriptionPlan

def setup_plans():
    plans = [
        {
            "name": "الخطة المجانية",
            "description": "مثالية للمبتدئين لتجربة المتجر وإضافة عدد محدود من المنتجات",
            "price_monthly": 0.00,
            "price_yearly": 0.00,
            "max_products": 5,
            "max_employees": 1,
            "max_monthly_orders": 20,
            "max_storage_mb": 50,
            "max_coupons": 2,
            "custom_domain_enabled": False,
            "remove_branding_enabled": False,
            "api_access_enabled": False,
            "advanced_reports_enabled": False,
        },
        {
            "name": "الخطة الأساسية",
            "description": "للمتاجر النامية التي تحتاج إلى منتجات ومبيعات أكثر وربط دومين مخصص",
            "price_monthly": 19.00,
            "price_yearly": 190.00,
            "max_products": 50,
            "max_employees": 3,
            "max_monthly_orders": 500,
            "max_storage_mb": 500,
            "max_coupons": 10,
            "custom_domain_enabled": True,
            "remove_branding_enabled": False,
            "api_access_enabled": False,
            "advanced_reports_enabled": True,
        },
        {
            "name": "الخطة الاحترافية",
            "description": "للمتاجر المحترفة التي تبيع بكثافة وتريد إزالة العلامة المائية للعلامة التجارية",
            "price_monthly": 49.00,
            "price_yearly": 490.00,
            "max_products": 9999,
            "max_employees": 99,
            "max_monthly_orders": 99999,
            "max_storage_mb": 5000,
            "max_coupons": 99,
            "custom_domain_enabled": True,
            "remove_branding_enabled": True,
            "api_access_enabled": True,
            "advanced_reports_enabled": True,
        },
        {
            "name": "خطة المؤسسات",
            "description": "الحل الشامل للمؤسسات الكبرى مع دعم فني مخصص وموارد غير محدودة",
            "price_monthly": 149.00,
            "price_yearly": 1490.00,
            "max_products": 99999,
            "max_employees": 999,
            "max_monthly_orders": 999999,
            "max_storage_mb": 50000,
            "max_coupons": 999,
            "custom_domain_enabled": True,
            "remove_branding_enabled": True,
            "api_access_enabled": True,
            "advanced_reports_enabled": True,
        }
    ]

    for p in plans:
        obj, created = SubscriptionPlan.objects.get_or_create(
            name=p["name"],
            defaults=p
        )
        if created:
            print("Created subscription plan successfully")
        else:
            print("Plan already exists.")

if __name__ == "__main__":
    setup_plans()
