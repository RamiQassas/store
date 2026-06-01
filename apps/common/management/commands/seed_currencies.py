from django.core.management.base import BaseCommand
from apps.common.models import Currency

class Command(BaseCommand):
    help = "Seeds initial platform currencies (USD, TRY, SYP)"

    def handle(self, *args, **options):
        # 1. USD (Base/Default)
        usd, created = Currency.objects.get_or_create(
            code="USD",
            defaults={
                "name": "US Dollar",
                "symbol": "$",
                "exchange_rate": 1.0,
                "is_default": True,
                "is_active": True,
                "decimal_places": 2
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created currency: USD (Default)"))

        # 2. TRY (Turkish Lira)
        try_curr, created = Currency.objects.get_or_create(
            code="TRY",
            defaults={
                "name": "Turkish Lira",
                "symbol": "₺",
                "exchange_rate": 32.50,
                "is_default": False,
                "is_active": True,
                "decimal_places": 2
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created currency: TRY"))

        # 3. SYP (Syrian Pound)
        syp, created = Currency.objects.get_or_create(
            code="SYP",
            defaults={
                "name": "Syrian Pound",
                "symbol": "£S",
                "exchange_rate": 15000.0,
                "is_default": False,
                "is_active": True,
                "decimal_places": 2
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created currency: SYP"))

        self.stdout.write(self.style.SUCCESS("Currency seeding completed successfully."))
