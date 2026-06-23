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

    def test_create_physical_order_requires_shipping(self):
        # Create physical product and variant
        category = Category.objects.create(name="Physical Category")
        product = Product.objects.create(name="T-Shirt", category=category, product_type="physical", is_active=True)
        variant = ProductVariant.objects.create(product=product, name="Large Size", sku="TSHIRT-L", price=Decimal("3.00"), is_active=True)

        client = APIClient()
        client.force_authenticate(self.user)
        
        # Test missing shipping info
        response = client.post(
            "/api/orders/",
            {"variant_id": str(variant.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("جميع حقول الشحن والتوصيل مطلوبة", str(response.data))

    def test_create_physical_order_success(self):
        category = Category.objects.create(name="Physical Category")
        product = Product.objects.create(name="T-Shirt", category=category, product_type="physical", is_active=True)
        variant = ProductVariant.objects.create(product=product, name="Large Size", sku="TSHIRT-L", price=Decimal("3.00"), is_active=True)

        client = APIClient()
        client.force_authenticate(self.user)

        response = client.post(
            "/api/orders/",
            {
                "variant_id": str(variant.id), 
                "quantity": 1,
                "shipping_name": "احمد علي",
                "shipping_phone": "0500000000",
                "shipping_address": "الرياض، حي الياسمين، شارع العليا"
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.available_balance, Decimal("7.00")) # 10 - 3 = 7
        
        # Verify shipping fields are saved
        from apps.orders.models import Order
        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.shipping_name, "احمد علي")
        self.assertEqual(order.shipping_phone, "0500000000")
        self.assertEqual(order.shipping_address, "الرياض، حي الياسمين، شارع العليا")
        self.assertTrue(order.has_physical_products)

    def test_inventory_tracking(self):
        # 1. Enable inventory tracking on product
        product = self.variant.product
        product.track_inventory = True
        product.quantity = 5
        product.low_stock_threshold = 2
        product.save()

        client = APIClient()
        client.force_authenticate(self.user)

        # 2. Purchase 2 units
        response = client.post(
            "/api/orders/",
            {"variant_id": str(self.variant.id), "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        product.refresh_from_db()
        self.assertEqual(product.quantity, 3)
        self.assertFalse(product.is_out_of_stock)

        # 3. Try to purchase 4 units (insufficient stock)
        credit_wallet(self.user.wallet.id, Decimal("50.00"), reference="test-credit-2")
        
        response = client.post(
            "/api/orders/",
            {"variant_id": str(self.variant.id), "quantity": 4},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        product.refresh_from_db()
        self.assertEqual(product.quantity, 3)

        # 4. Purchase remaining 3 units (runs out of stock)
        response = client.post(
            "/api/orders/",
            {"variant_id": str(self.variant.id), "quantity": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        product.refresh_from_db()
        self.assertEqual(product.quantity, 0)
        self.assertTrue(product.is_out_of_stock)
