from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.wallets.services import get_or_create_wallet


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created:
        get_or_create_wallet(instance)
