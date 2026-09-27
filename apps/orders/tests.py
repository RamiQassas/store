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


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class ProviderProductAvailabilityTests(TestCase):
    def setUp(self):
        from apps.providers.models import ProviderProfile, ProviderProduct, ProviderMapping
        self.user = User.objects.create_user(email="buyer_avail@example.com", password="StrongPass12345")
        credit_wallet(self.user.wallet.id, Decimal("50.00"), reference="test-credit")

        self.profile = ProviderProfile.objects.create(
            provider_name="رقميات",
            base_url="https://api.alkasr-vip.com/client/api/",
            api_token="TEST_TOKEN",
            is_active=True
        )
        self.category = Category.objects.create(name="العاب")
        self.product = Product.objects.create(name="ببجي موبايل", category=self.category, is_active=True, is_out_of_stock=False)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="60 شدة",
            sku="PRV-TEST-60",
            price=Decimal("1.00"),
            cost=Decimal("0.90"),
            is_active=True,
            is_temporarily_disabled=False
        )
        self.provider_product = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="6001",
            name="60 UC Global",
            cost_price=Decimal("0.90"),
            is_active=True,
            local_is_active=True
        )
        self.mapping = ProviderMapping.objects.create(
            local_product=self.product,
            local_variant=self.variant,
            provider_product=self.provider_product
        )

    def test_mark_variant_unavailable_direct(self):
        from apps.orders.services import mark_variant_unavailable
        mark_variant_unavailable(self.variant, reason="Product Unavailable from Provider", error_code=110)

        self.variant.refresh_from_db()
        self.provider_product.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(self.variant.is_active)
        self.assertTrue(self.variant.is_temporarily_disabled)
        self.assertFalse(self.provider_product.is_active)
        self.assertFalse(self.provider_product.local_is_active)
        self.assertTrue(self.product.is_out_of_stock)

    def test_create_order_fails_immediately_for_inactive_variant(self):
        from apps.orders.services import create_order
        self.variant.is_active = False
        self.variant.is_temporarily_disabled = True
        self.variant.save()

        with self.assertRaises(ValueError) as ctx:
            create_order(self.user, str(self.variant.id), quantity=1)
        self.assertIn("غير متوفر", str(ctx.exception))

    def test_create_pending_gateway_order_fails_for_inactive_variant(self):
        from apps.orders.services import create_pending_gateway_order
        self.variant.is_temporarily_disabled = True
        self.variant.save()

        with self.assertRaises(ValueError) as ctx:
            create_pending_gateway_order(self.user, str(self.variant.id), quantity=1, gateway_code="paymera")
        self.assertIn("غير متوفر", str(ctx.exception))

    def test_order_placement_deactivates_variant_on_code_110(self):
        from unittest.mock import patch
        from services.provider.alkasr.exceptions import ProductUnavailableException
        from apps.orders.services import create_order

        with patch("services.provider.manager.ProviderManager.place_order", side_effect=ProductUnavailableException(code=110)):
            order = create_order(
                customer=self.user,
                variant_id=str(self.variant.id),
                quantity=1,
                fulfillment_data={"player_id": "12345"}
            )

        self.variant.refresh_from_db()
        self.provider_product.refresh_from_db()
        self.product.refresh_from_db()

        # Variant and provider product must be immediately deactivated!
        self.assertFalse(self.variant.is_active)
        self.assertTrue(self.variant.is_temporarily_disabled)
        self.assertFalse(self.provider_product.is_active)
        self.assertTrue(self.product.is_out_of_stock)
        self.assertEqual(order.status, "cancelled")

    def test_apply_provider_status_cancellation_deactivates_variant(self):
        from apps.orders.models import Order, OrderItem
        from apps.orders.provider_status import apply_provider_status

        order = Order.objects.create(
            customer=self.user,
            number="ORD-TEST-UNAVAIL",
            status=Order.Status.PROCESSING,
            total_amount=Decimal("1.00"),
            original_total=Decimal("1.00"),
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            quantity=1,
            unit_price=Decimal("1.00"),
            unit_cost=Decimal("0.90"),
            total_price=Decimal("1.00")
        )

        apply_provider_status(
            order,
            provider_status="reject",
            raw_response={"code": 110, "error": "Product Unavailable"},
            actor=self.user
        )

        self.variant.refresh_from_db()
        self.provider_product.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(self.variant.is_active)
        self.assertTrue(self.variant.is_temporarily_disabled)
        self.assertFalse(self.provider_product.is_active)
        self.assertTrue(self.product.is_out_of_stock)

