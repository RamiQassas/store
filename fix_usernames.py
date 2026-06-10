from apps.accounts.models import User
from django.db import transaction

def fix_usernames():
    with transaction.atomic():
        users = User.objects.filter(username='')
        print(f"Fixing {users.count()} empty usernames...")
        for u in users:
            u.username = f"user_{str(u.id)[:8]}"
            u.save(update_fields=['username'])
            print(f"Updated user {u.email} -> {u.username}")

if __name__ == "__main__":
    fix_usernames()
