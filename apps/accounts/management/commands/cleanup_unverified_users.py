from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User

class Command(BaseCommand):
    help = "Deletes unverified user accounts that are older than 24 hours."

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(hours=24)
        
        # Select unverified users created more than 24 hours ago
        unverified_users = User.objects.filter(
            email_verified=False,
            date_joined__lt=threshold
        )
        
        count = unverified_users.count()
        
        if count > 0:
            emails = list(unverified_users.values_list('email', flat=True))
            unverified_users.delete()
            self.stdout.write(
                self.style.SUCCESS(f"Successfully deleted {count} unverified accounts: {', '.join(emails)}")
            )
        else:
            self.stdout.write(self.style.SUCCESS("No unverified accounts older than 24 hours found."))
