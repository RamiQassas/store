from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.wallets.models import Wallet

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    }
}


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class AccountApiTests(TestCase):
    def test_register_creates_user_wallet_and_tokens(self):
        client = APIClient()
        response = client.post(
            "/api/auth/register/",
            {"email": "new@example.com", "password": "StrongPass12345", "first_name": "New"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data["tokens"])
        self.assertTrue(Wallet.objects.filter(user__email="new@example.com").exists())

    def test_regular_user_cannot_open_control_dashboard(self):
        client = APIClient()
        user = User.objects.create_user(email="buyer@example.com", password="StrongPass12345")
        client.force_authenticate(user=user)
        response = client.get("/control/")

        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(user.is_staff)

    def test_api_lookup_user_by_name(self):
        client = APIClient()
        searcher = User.objects.create_user(email="searcher@example.com", password="StrongPass12345")
        client.force_login(searcher)
        
        # Create target user
        User.objects.create_user(
            email="target@example.com", 
            password="StrongPass12345", 
            first_name="محمد", 
            last_name="أحمد",
            uid="987654"
        )
        
        # Search by full name
        response = client.get("/api/users/lookup/", {"q": "محمد أحمد"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uid"], "987654")
        
        # Search by first name (single match)
        response = client.get("/api/users/lookup/", {"q": "محمد"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uid"], "987654")

    def test_api_lookup_user_duplicates(self):
        client = APIClient()
        searcher = User.objects.create_user(email="searcher2@example.com", password="StrongPass12345")
        client.force_login(searcher)
        
        # Create two users with the same first name
        User.objects.create_user(email="t1@example.com", password="StrongPass12345", first_name="علي", last_name="حسين", uid="111")
        User.objects.create_user(email="t2@example.com", password="StrongPass12345", first_name="علي", last_name="رضا", uid="222")
        
        # Search by "علي" should fail with 400 (multiple matches)
        response = client.get("/api/users/lookup/", {"q": "علي"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("أكثر من مستخدم", response.json()["error"])
        
        # Search by full name "علي حسين" should succeed (single match)
        response = client.get("/api/users/lookup/", {"q": "علي حسين"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uid"], "111")

    def test_control_db_maintenance_protects_admin(self):
        from django.urls import reverse
        from apps.stores.models import Store, SubscriptionPlan
        from apps.common.tenant_utils import bypass_tenant_filter

        # Create a superuser
        admin = User.objects.create_superuser(email="superadmin@example.com", password="Password123!")

        with bypass_tenant_filter():
            # Create a store linked to the admin
            plan = SubscriptionPlan.objects.create(
                name="Free Plan",
                price_monthly=0,
                price_yearly=0,
                max_products=10,
                max_employees=5,
                max_monthly_orders=100
            )
            store = Store.objects.create(
                owner=admin,
                name="Admin Test Store",
                subdomain="admin-test",
                subscription_plan=plan,
                is_active=True
            )
            # Link admin to the store to simulate the cascade delete risk
            admin.store = store
            admin.save()

        client = APIClient()
        client.force_login(admin)

        # Post cleanup for stores and users
        response = client.post(reverse("control_db_maintenance"), {
            "action": "cleanup",
            "targets": ["stores", "users"]
        })
        self.assertEqual(response.status_code, 302)

        with bypass_tenant_filter():
            # Verify store is deleted
            self.assertFalse(Store.objects.filter(id=store.id).exists())

            # Verify admin still exists and was not deleted by cascade or user cleanup
            admin_refreshed = User.objects.filter(id=admin.id).first()
            self.assertIsNotNone(admin_refreshed)
            self.assertEqual(admin_refreshed.email, "superadmin@example.com")
            self.assertIsNone(admin_refreshed.store)

    def test_control_db_maintenance_coupons_cleanup(self):
        from django.urls import reverse
        from apps.orders.models import Coupon
        from apps.common.tenant_utils import bypass_tenant_filter

        admin = User.objects.create_superuser(email="superadmin2@example.com", password="Password123!")

        with bypass_tenant_filter():
            coupon = Coupon.objects.create(
                code="CLEANUPTEST",
                discount_percent=10,
                is_active=True
            )

        client = APIClient()
        client.force_login(admin)

        # Post cleanup for coupons
        response = client.post(reverse("control_db_maintenance"), {
            "action": "cleanup",
            "targets": ["coupons"]
        })
        self.assertEqual(response.status_code, 302)

        with bypass_tenant_filter():
            # Verify coupon is deleted
            self.assertFalse(Coupon.objects.filter(id=coupon.id).exists())


