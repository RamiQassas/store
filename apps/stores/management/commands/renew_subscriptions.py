from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.stores.models import Store
from apps.common.tenant_utils import bypass_tenant_filter

class Command(BaseCommand):
    help = "Renew expiring store subscriptions automatically using owner wallets."

    def handle(self, *args, **options):
        self.stdout.write("Starting store subscription renewals check...")
        
        # Bypass tenant filtering to query all stores
        with bypass_tenant_filter():
            expiring_stores = Store.unfiltered.filter(
                is_active=True,
                auto_renew=True,
                subscription_end__lte=timezone.now()
            )
            
            total_count = expiring_stores.count()
            self.stdout.write(f"Found {total_count} stores with auto-renew enabled and expired/expiring subscription.")
            
            success_count = 0
            fail_count = 0
            
            for store in expiring_stores:
                self.stdout.write(f"Attempting to renew store: {store.name} (Subdomain: {store.subdomain})")
                renewed = store.renew_subscription()
                if renewed:
                    self.stdout.write(self.style.SUCCESS(f"Successfully renewed store: {store.name}"))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to renew store: {store.name}. Store has been suspended."))
                    fail_count += 1
                    
        self.stdout.write(f"Renewal check finished. Success: {success_count}, Suspended/Failed: {fail_count}")
