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
