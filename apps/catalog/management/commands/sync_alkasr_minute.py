import logging
from django.core.management.base import BaseCommand
from apps.accounts.tasks import sync_alkasr_catalog_periodic_task, sync_pending_api_orders_task

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Synchronizes catalog with Alkasr VIP provider and checks pending API orders."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Running Alkasr 1-minute catalog sync..."))
        catalog_res = sync_alkasr_catalog_periodic_task()
        self.stdout.write(self.style.SUCCESS(f"Catalog sync result: {catalog_res}"))

        self.stdout.write(self.style.NOTICE(">> Running pending API orders status check..."))
        orders_res = sync_pending_api_orders_task()
        self.stdout.write(self.style.SUCCESS(f"Orders sync result: {orders_res}"))
