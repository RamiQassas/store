from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = "Initializes Role-Based Access Control (RBAC) groups and permissions."

    def handle(self, *args, **options):
        # Define roles and their permissions (app_label, model_name, codename)
        roles = {
            "Super Admin": {
                "description": "Full access to all systems.",
                "all_perms": True
            },
            "Financial Manager": {
                "description": "Manage wallets, deposits, withdrawals, and currencies.",
                "perms": [
                    ("wallets", "wallet", ["view", "change"]),
                    ("wallets", "ledgerentry", ["view"]),
                    ("wallets", "wallettransaction", ["view"]),
                    ("payments", "depositrequest", ["view", "change"]),
                    ("payments", "withdrawalrequest", ["view", "change"]),
                    ("payments", "paymentmethod", ["view", "add", "change"]),
                    ("common", "currency", ["view", "add", "change", "delete"]),
                ]
            },
            "Support Agent": {
                "description": "Handle customer support tickets and chat.",
                "perms": [
                    ("support", "ticket", ["view", "add", "change"]),
                    ("support", "ticketmessage", ["view", "add"]),
                    ("accounts", "user", ["view"]),
                ]
            },
            "Product Manager": {
                "description": "Manage products, categories, and variants.",
                "perms": [
                    ("catalog", "product", ["view", "add", "change", "delete"]),
                    ("catalog", "category", ["view", "add", "change", "delete"]),
                    ("catalog", "productvariant", ["view", "add", "change", "delete"]),
                ]
            },
            "Moderator": {
                "description": "Manage users and moderate content.",
                "perms": [
                    ("accounts", "user", ["view", "change"]),
                    ("accounts", "moderationlog", ["view"]),
                    ("common", "systemauditlog", ["view"]),
                ]
            }
        }

        for role_name, data in roles.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {role_name}"))
            
            if data.get("all_perms"):
                # Assign all permissions for Super Admin
                all_perms = Permission.objects.all()
                group.permissions.set(all_perms)
            else:
                group.permissions.clear()
                for app_label, model_name, actions in data.get("perms", []):
                    try:
                        content_type = ContentType.objects.get(app_label=app_label, model=model_name)
                        for action in actions:
                            codename = f"{action}_{model_name}"
                            perm = Permission.objects.get(content_type=content_type, codename=codename)
                            group.permissions.add(perm)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"Could not assign permission {action}_{model_name}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS("RBAC initialization complete."))
