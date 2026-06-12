import os
import django
from django.conf import settings

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.payments.models import PaymentMethod

methods = PaymentMethod.objects.all()
for m in methods:
    print(f"Name: {m.name}, Active: {m.is_active}, Can Deposit: {m.can_deposit}, Can Withdraw: {m.can_withdraw}")
