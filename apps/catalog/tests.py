from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from apps.catalog.models import Category, Product, ProductVariant, ProductKey
from apps.orders.services import create_order
from apps.orders.models import Order
from apps.wallets.services import credit_wallet

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    }
}

@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class AutoDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="StrongPass12345")
        category = Category.objects.create(name="Keys Category")
        product = Product.objects.create(name="Netflix Card", category=category, is_active=True)
        self.variant = ProductVariant.objects.create(
            product=product,
            name="1 Month Premium",
            sku="NETFLIX-1M-TEST",
            price=Decimal("10.00"),
            is_active=True,
            delivery_type="keys"
        )
        self.key1 = ProductKey.objects.create(variant=self.variant, key_code="KEY-NETFLIX-001")
        self.key2 = ProductKey.objects.create(variant=self.variant, key_code="KEY-NETFLIX-002")
        credit_wallet(self.user.wallet.id, Decimal("50.00"), reference="test-credit")

    def test_auto_delivery_success(self):
        order = create_order(customer=self.user, variant_id=self.variant.id, quantity=1)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIn('keys', order.fulfillment_data)
        self.assertEqual(len(order.fulfillment_data['keys']), 1)
        allocated_key_code = order.fulfillment_data['keys'][0]
        
        allocated_key = ProductKey.objects.get(key_code=allocated_key_code)
        self.assertTrue(allocated_key.is_used)
        self.assertEqual(allocated_key.used_by, self.user)
        self.assertEqual(allocated_key.order, order)
        self.assertIsNotNone(allocated_key.used_at)

        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.available_balance, Decimal("40.00"))

    def test_auto_delivery_out_of_stock(self):
        with self.assertRaises(ValueError) as ctx:
            create_order(customer=self.user, variant_id=self.variant.id, quantity=3)
        
        self.assertIn("المخزون غير كافي", str(ctx.exception))
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.available_balance, Decimal("50.00"))
        
        self.key1.refresh_from_db()
        self.key2.refresh_from_db()
        self.assertFalse(self.key1.is_used)
        self.assertFalse(self.key2.is_used)

    def test_auto_delivery_exact_stock_consumption(self):
        order = create_order(self.user, self.variant.id, quantity=2)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(len(order.fulfillment_data['keys']), 2)
        self.assertEqual(ProductKey.objects.filter(variant=self.variant, is_used=False).count(), 0)
        
        with self.assertRaises(ValueError):
            create_order(self.user, self.variant.id, quantity=1)


from django.urls import reverse

@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class PurchaseSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer_sec@example.com", password="StrongPass12345")
        category = Category.objects.create(name="Security Keys Category")
        product = Product.objects.create(name="Netflix Security Card", category=category, is_active=True)
        self.variant = ProductVariant.objects.create(
            product=product,
            name="1 Month Premium Sec",
            sku="NETFLIX-1M-SEC-TEST",
            price=Decimal("10.00"),
            is_active=True,
            delivery_type="keys"
        )
        self.key1 = ProductKey.objects.create(variant=self.variant, key_code="KEY-SEC-001")
        self.key2 = ProductKey.objects.create(variant=self.variant, key_code="KEY-SEC-002")
        credit_wallet(self.user.wallet.id, Decimal("50.00"), reference="test-credit")

    def test_purchase_with_email_verification(self):
        # Enable security trigger for purchase
        self.user.security_purchase_method = "EMAIL"
        self.user.save()
        
        # Log in the user
        self.client.force_login(self.user)
        
        # Attempt purchase
        purchase_url = reverse("product_detail", kwargs={"pk": self.variant.product.id})
        response = self.client.post(purchase_url, {"variant_id": self.variant.id})
        
        # Should redirect to OTP verification page
        self.assertRedirects(response, reverse("site_verify_otp"))
        
        # Session should contain pending purchase
        session = self.client.session
        self.assertIn("v3_pending_purchase", session)
        self.assertEqual(session["v3_pending_purchase"]["variant_id"], str(self.variant.id))
        
        # Find the last OTP generated in database
        from apps.accounts.models import OTPToken
        otp = OTPToken.objects.filter(user=self.user, purpose="purchase").order_by("-created_at").first()
        self.assertIsNotNone(otp)
        
        # Verify the OTP code
        verify_url = reverse("site_verify_otp")
        verify_response = self.client.post(verify_url, {"code": otp.code})
        
        # Should redirect to order detail page upon successful verification and purchase completion
        order = Order.objects.filter(customer=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertIn("keys", order.fulfillment_data)
        
        order_detail_url = reverse("dashboard_order_detail", kwargs={"pk": order.id})
        self.assertRedirects(verify_response, order_detail_url)
        
        # Session keys should be cleaned up
        session_after = self.client.session
        self.assertNotIn("v3_pending_purchase", session_after)
        self.assertNotIn("v3_auth_uid", session_after)
