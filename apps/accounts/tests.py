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
