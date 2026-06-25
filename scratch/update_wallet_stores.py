import os
import sys
sys.path.append(os.getcwd())

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.wallets.models import Wallet
from django.db import transaction

with transaction.atomic():
    wallets = Wallet.all_objects.select_related('user').all()
    updated = 0
    for w in wallets:
        if w.user.store_id and w.store_id != w.user.store_id:
            w.store_id = w.user.store_id
            w.save(update_fields=['store'])
            updated += 1
    print(f"Updated {updated} wallets to match their user's store.")
