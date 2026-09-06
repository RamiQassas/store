from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from apps.stores.models import Store, SubscriptionPlan, StoreEmployee
from apps.accounts.models import OTPToken, KYCSettings
from apps.common.tenant_utils import bypass_tenant_filter
from unittest.mock import patch
from apps.common.models import Currency

User = get_user_model()

@override_settings(SECURE_SSL_REDIRECT=False, SITE_URL="http://testserver", ALLOWED_HOSTS=["testserver", ".testserver"])
class SubStoreLoginOtpTest(TestCase):
    def setUp(self):
        self.otp_patcher = patch("apps.site.views.v3_send_otp_email", return_value=True)
        self.otp_patcher.start()
        self.addCleanup(self.otp_patcher.stop)
        with bypass_tenant_filter():
            self.currency = Currency.objects.create(
                name="US Dollar",
                code="USD",
                symbol="$",
                buy_rate=1.0,
                sell_rate=1.0,
                is_default=True
            )
            self.plan = SubscriptionPlan.objects.create(
                name="Basic Plan",
                price_monthly=10.0,
                is_active=True
            )
            # Store Owner
            self.owner = User.objects.create_user(
                email="owner@testsubstore.com",
                password="OwnerPassword123!",
                role="verified_merchant"
            )
            self.store = Store.objects.create(
                owner=self.owner,
                name="Test SubStore",
                subdomain="mysubstore",
                subscription_plan=self.plan,
                is_active=True
            )
            StoreEmployee.objects.create(store=self.store, user=self.owner, role="owner")

            # Direct Customer of this store
            self.customer = User.objects.create_user(
                email="customer@testsubstore.com",
                password="CustomerPassword123!",
                store=self.store
            )

    def test_customer_login_and_otp_redirects_to_dashboard(self):
        """Verify that customer can login with OTP and cleanly reach dashboard, never redirected back to login."""
        client = Client()

        # 1. GET login page
        r1 = client.get("/auth/login/", HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r1.status_code, 200)

        # 2. POST login credentials
        r2 = client.post("/auth/login/", {
            "email": "customer@testsubstore.com",
            "password": "CustomerPassword123!",
        }, HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r2.status_code, 302)
        self.assertIn("/auth/verify-otp/", r2.headers["Location"])

        # 3. GET OTP page
        r3 = client.get("/auth/verify-otp/", HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r3.status_code, 200)

        # Retrieve generated OTP
        otp_obj = OTPToken.objects.filter(user=self.customer, is_used=False).order_by("-created_at").first()
        self.assertIsNotNone(otp_obj)

        # 4. POST OTP
        r4 = client.post("/auth/verify-otp/", {
            "code": otp_obj.code,
            "action": "verify"
        }, HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r4.status_code, 302)
        self.assertNotIn("/auth/login/", r4.headers["Location"])
        self.assertIn("/dashboard/", r4.headers["Location"])

        # 5. Follow to dashboard
        r5 = client.get(r4.headers["Location"], HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r5.status_code, 200)

    def test_already_authenticated_user_on_otp_page_does_not_redirect_to_login(self):
        """If user is already authenticated and hits /auth/verify-otp/, they must go to dashboard, not login."""
        client = Client()
        client.force_login(self.customer, backend='apps.stores.auth_backend.TenantModelBackend')

        response = client.get("/auth/verify-otp/", HTTP_HOST="mysubstore.testserver")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/auth/login/", response.headers["Location"])
        self.assertIn("/dashboard/", response.headers["Location"])

    def test_safe_redirect_prevents_redirecting_back_to_auth_login(self):
        """Even if next param was set to /auth/login/?next=..., verification must not redirect back to /auth/login/."""
        client = Client()

        # Login with next param pointing to login page
        client.post("/auth/login/?next=/auth/login/?next=/dashboard/", {
            "email": "customer@testsubstore.com",
            "password": "CustomerPassword123!",
        }, HTTP_HOST="mysubstore.testserver")

        otp_obj = OTPToken.objects.filter(user=self.customer, is_used=False).order_by("-created_at").first()
        r_otp = client.post("/auth/verify-otp/", {
            "code": otp_obj.code,
            "action": "verify"
        }, HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r_otp.status_code, 302)
        self.assertEqual(r_otp.headers["Location"], "/dashboard/")

    def test_store_owner_can_login_to_substore(self):
        """Store owner (who has store_id=None) can log into their sub-store without getting kicked out."""
        client = Client()

        r_post = client.post("/auth/login/", {
            "email": "owner@testsubstore.com",
            "password": "OwnerPassword123!",
        }, HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r_post.status_code, 302)
        self.assertIn("/auth/verify-otp/", r_post.headers["Location"])

        otp_obj = OTPToken.objects.filter(user=self.owner, is_used=False).order_by("-created_at").first()
        r_otp = client.post("/auth/verify-otp/", {
            "code": otp_obj.code,
            "action": "verify"
        }, HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r_otp.status_code, 302)
        self.assertIn("/dashboard/", r_otp.headers["Location"])

        r_dash = client.get("/dashboard/", HTTP_HOST="mysubstore.testserver")
        self.assertEqual(r_dash.status_code, 200)
