from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product, ProductFormField, ProductVariant
from apps.payments.models import PaymentMethod
from apps.services.models import Service, ServiceField


class Command(BaseCommand):
    help = "Create starter categories, products, payment methods, and services."

    def handle(self, *args, **options):
        games, _ = Category.objects.get_or_create(name="شحن ألعاب", slug="game-topups")
        subs, _ = Category.objects.get_or_create(name="اشتراكات", slug="subscriptions")
        cards, _ = Category.objects.get_or_create(name="بطاقات رقمية", slug="gift-cards")

        pubg, _ = Product.objects.get_or_create(
            name="PUBG UC",
            slug="pubg-uc",
            defaults={
                "category": games,
                "description": "شحن شدات PUBG عبر ID والمنطقة.",
                "instructions": "أدخل ID اللاعب والمنطقة بدقة قبل تأكيد الطلب.",
                "delivery_type": Product.DeliveryType.CUSTOM_FORM,
                "is_featured": True,
            },
        )
        ProductFormField.objects.update_or_create(
            product=pubg,
            key="player_id",
            defaults={"label": "معرّف اللاعب", "field_type": "text"},
        )
        ProductFormField.objects.update_or_create(
            product=pubg,
            key="region",
            defaults={"label": "المنطقة", "field_type": "select", "options": ["عالمي", "الشرق الأوسط", "آسيا"]},
        )
        for name, price, sku in [
            ("60 UC", "1.20", "PUBG-60"),
            ("325 UC", "5.80", "PUBG-325"),
            ("660 UC", "11.20", "PUBG-660"),
            ("1800 UC", "28.50", "PUBG-1800"),
            ("3850 UC", "57.00", "PUBG-3850"),
        ]:
            ProductVariant.objects.get_or_create(product=pubg, sku=sku, defaults={"name": name, "price": Decimal(price), "estimated_delivery_minutes": 30})

        Product.objects.get_or_create(name="YouTube Premium", slug="youtube-premium", defaults={"category": subs, "delivery_type": Product.DeliveryType.MANUAL})
        Product.objects.get_or_create(name="Gift Card", slug="gift-card", defaults={"category": cards, "delivery_type": Product.DeliveryType.AUTOMATIC})

        PaymentMethod.objects.get_or_create(
            name="شام كاش",
            method_type=PaymentMethod.MethodType.MOBILE_PAYMENT,
            defaults={
                "provider_name": "Sham Cash",
                "account_number": "0912345678",
                "account_name": "Raqamiyat Store",
                "instructions": "يرجى تحويل المبلغ إلى الرقم المذكور وإرفاق وصل العملية.",
                "min_deposit": Decimal("1000"),
                "max_deposit": Decimal("1000000"),
            }
        )
        PaymentMethod.objects.get_or_create(
            name="تحويل بنكي",
            method_type=PaymentMethod.MethodType.BANK,
            defaults={
                "provider_name": "بنك بيمو",
                "account_number": "123456789",
                "account_name": "Raqamiyat Store",
                "iban": "SY000123456789000000",
                "instructions": "يرجى التحويل إلى حسابنا البنكي وإرفاق إشعار التحويل.",
                "min_deposit": Decimal("50000"),
                "max_deposit": Decimal("10000000"),
            }
        )

        service, _ = Service.objects.get_or_create(
            name="دفع فواتير",
            slug="bill-payment",
            defaults={"service_type": Service.ServiceType.BILL_PAYMENT, "description": "خدمة قابلة للتوسع لدفع الفواتير لاحقا."},
        )
        ServiceField.objects.get_or_create(service=service, key="account_number", defaults={"label": "رقم الحساب"})

        self.stdout.write(self.style.SUCCESS("Demo data created with new PaymentMethods."))
