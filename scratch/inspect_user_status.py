import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User

users = User.objects.all()
print(f"Total users: {users.count()}")
for u in users:
    print(f"- {u.email} (Username: {u.username}, Active: {u.is_active}, Store: {u.store})")
