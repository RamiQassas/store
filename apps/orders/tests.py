from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant
from apps.wallets.services import credit_wallet

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    }
}


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class OrderApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="StrongPass12345")
        category = Category.objects.create(name="Games")
        product = Product.objects.create(name="PUBG UC", category=category, is_active=True)
        self.variant = ProductVariant.objects.create(product=product, name="60 UC", sku="PUBG-60-TEST", price=Decimal("5.00"), is_active=True)
        credit_wallet(self.user.wallet.id, Decimal("10.00"), reference="test-credit")

    def test_create_order_debits_wallet(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            "/api/orders/",
            {"variant_id": str(self.variant.id), "quantity": 1, "fulfillment_data": {"player_id": "123", "region": "global"}},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.available_balance, Decimal("5.00"))
