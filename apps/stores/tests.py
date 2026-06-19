from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model, authenticate
from apps.stores.models import Store, SubscriptionPlan, StoreEmployee
from apps.catalog.models import Product, Category, ProductVariant
from apps.orders.models import Order
from apps.wallets.models import Wallet
from apps.common.models import Currency
from apps.common.tenant_utils import set_current_store, bypass_tenant_filter, _current_store

User = get_user_model()


class StoreMultiTenantTest(TestCase):
    def setUp(self):
        # Create standard currency
        self.currency = Currency.objects.create(
            name="US Dollar",
            code="USD",
            symbol="$",
            buy_rate=1.0,
            sell_rate=1.0,
            is_default=True
        )

        # Create plans
        self.free_plan = SubscriptionPlan.objects.create(
            name="Free Plan",
            max_products=2,
            max_employees=1,
            max_monthly_orders=2,
            is_active=True
        )

        # Create platform admin and owners under bypass context
        with bypass_tenant_filter():
            self.super_admin = User.objects.create_superuser(
                email="superadmin@raqamiyatapp.com",
                password="SuperPassword123!"
            )

            self.owner_a = User.objects.create_user(
                email="owner_a@example.com",
                password="OwnerPassword123!"
            )
            
        self.store_a = Store.objects.create(
            owner=self.owner_a,
            name="Store A",
            slug="store-a",
            subscription_plan=self.free_plan,
            is_active=True
        )
        StoreEmployee.objects.create(store=self.store_a, user=self.owner_a, role="owner")

        # Create store B owner & store B
        with bypass_tenant_filter():
            self.owner_b = User.objects.create_user(
                email="owner_b@example.com",
                password="OwnerPassword123!"
            )
        self.store_b = Store.objects.create(
            owner=self.owner_b,
            name="Store B",
            slug="store-b",
            subscription_plan=self.free_plan,
            is_active=True
        )
        StoreEmployee.objects.create(store=self.store_b, user=self.owner_b, role="owner")

        # Create categories & products
        with bypass_tenant_filter():
            self.cat_main = Category.objects.create(name="Main Category", store=None)
            self.prod_main = Product.objects.create(name="Main Product", category=self.cat_main, store=None, is_active=True)

            self.cat_a = Category.objects.create(name="Cat A", store=self.store_a)
            self.prod_a = Product.objects.create(name="Prod A", category=self.cat_a, store=self.store_a, is_active=True)

            self.cat_b = Category.objects.create(name="Cat B", store=self.store_b)
            self.prod_b = Product.objects.create(name="Prod B", category=self.cat_b, store=self.store_b, is_active=True)

    def test_database_isolation_by_default(self):
        """Verifies that the default manager TenantManager isolates data correctly."""
        # 1. By default, with no active store in thread context, only main site data is visible
        main_products = list(Product.objects.all())
        self.assertEqual(len(main_products), 1)
        self.assertEqual(main_products[0].name, "Main Product")

        # 2. When store A is active in thread-local, only store A data is visible
        token = set_current_store(self.store_a)
        try:
            store_a_products = list(Product.objects.all())
            self.assertEqual(len(store_a_products), 1)
            self.assertEqual(store_a_products[0].name, "Prod A")
        finally:
            _current_store.reset(token)

        # 3. When store B is active in thread-local, only store B data is visible
        token = set_current_store(self.store_b)
        try:
            store_b_products = list(Product.objects.all())
            self.assertEqual(len(store_b_products), 1)
            self.assertEqual(store_b_products[0].name, "Prod B")
        finally:
            _current_store.reset(token)

    def test_unfiltered_manager(self):
        """Verifies that all_objects manager can fetch all records across all tenants."""
        with bypass_tenant_filter():
            all_prods = list(Product.all_objects.all())
            self.assertEqual(len(all_prods), 3)

    def test_auth_isolation(self):
        """Verifies login isolation across storefronts."""
        # Create a customer for store A
        with bypass_tenant_filter():
            customer_a = User.objects.create_user(
                email="cust_a@example.com",
                password="CustPassword123!",
                store=self.store_a
            )
        
        # Test authenticating customer A on store A front
        token = set_current_store(self.store_a)
        try:
            user = authenticate(username=customer_a.email, password="CustPassword123!")
            self.assertIsNotNone(user)
            self.assertEqual(user.email, customer_a.email)
        finally:
            _current_store.reset(token)

        # Test authenticating customer A on store B front (should fail)
        token = set_current_store(self.store_b)
        try:
            user = authenticate(username=customer_a.email, password="CustPassword123!")
            self.assertNullUser = user is None
            self.assertTrue(self.assertNullUser)
        finally:
            _current_store.reset(token)


class SaaSControlPanelAndLimitsTests(TestCase):
    def setUp(self):
        # Create standard currency
        self.currency = Currency.objects.create(
            name="US Dollar", code="USD", symbol="$", buy_rate=1.0, sell_rate=1.0, is_default=True
        )

        # Create subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name="Starter Plan",
            max_products=1,
            max_categories=1,
            max_monthly_orders=2,
            max_employees=1,
            is_active=True
        )

        # Create platform owner/admins
        with bypass_tenant_filter():
            self.super_admin = User.objects.create_superuser(
                email="superadmin@raqamiyatapp.com", password="SuperPassword123!"
            )
            self.owner = User.objects.create_user(
                email="owner@example.com", password="OwnerPassword123!"
            )

        self.store = Store.objects.create(
            owner=self.owner,
            name="My Store",
            slug="my-store",
            subscription_plan=self.plan,
            is_active=True
        )
        StoreEmployee.objects.create(store=self.store, user=self.owner, role="owner")

    def test_get_store_limit_respects_overrides(self):
        """Verifies get_store_limit reads manual overrides before plan defaults."""
        from apps.stores.views import get_store_limit
        
        # Without override: plan limit applies
        limit = get_store_limit(self.store, 'max_products')
        self.assertEqual(limit, 1)
        
        # With override: override takes precedence
        self.store.limit_overrides = {"max_products": 5}
        self.store.save()
        self.store.refresh_from_db()
        
        limit = get_store_limit(self.store, 'max_products')
        self.assertEqual(limit, 5)

    def test_products_limit_enforcement(self):
        """Verifies store limits prevent creating more products than plan allows.

        Uses Django's RequestFactory to call the view directly, injecting
        request.store manually. This cleanly tests the VIEW-LEVEL limit
        enforcement logic (get_store_limit) without relying on the full
        TenantMiddleware subdomain-routing stack, which is covered separately
        by the middleware unit tests.
        """
        from django.test import RequestFactory
        from apps.stores.views import merchant_product_form
        from apps.common.tenant_utils import set_current_store

        with bypass_tenant_filter():
            cat = Category.objects.create(name="Cat", store=self.store)
            Product.objects.create(name="Prod 1", category=cat, store=self.store, is_active=True)

        factory = RequestFactory()

        # --- Case 1: limit reached → view should redirect ---
        request = factory.get("/merchant/products/create/")
        request.user = self.owner          # logged-in store owner
        request.store = self.store         # middleware would normally set this
        request.urlconf = 'apps.stores.urls'  # needed for redirect() to resolve store URL names
        request.session = {}               # context processors need request.session
        # RequestFactory doesn't run MessageMiddleware, so attach cookie-based storage manually
        from django.contrib.messages.storage.cookie import CookieStorage
        request._messages = CookieStorage(request)
        # Set current tenant context so TenantManager filters correctly
        # Also set thread-level urlconf so redirect() → reverse() finds store URLs
        from django.urls import set_urlconf, get_urlconf
        original_urlconf = get_urlconf()
        token = set_current_store(self.store)
        set_urlconf('apps.stores.urls')
        try:
            response = merchant_product_form(request)
        finally:
            _current_store.reset(token)
            set_urlconf(original_urlconf)

        self.assertEqual(
            response.status_code, 302,
            f"Expected redirect (302) when product limit is reached, got {response.status_code}"
        )

        # --- Case 2: manual override applied → view should render the form ---
        self.store.limit_overrides = {"max_products": 3}
        self.store.save()
        self.store.refresh_from_db()

        request2 = factory.get("/merchant/products/create/")
        request2.user = self.owner
        request2.store = self.store        # now carries the refreshed limit_overrides
        request2.urlconf = 'apps.stores.urls'  # needed for URL resolution inside view
        request2.session = {}              # context processors need request.session
        request2._messages = CookieStorage(request2)

        token2 = set_current_store(self.store)
        set_urlconf('apps.stores.urls')
        try:
            response2 = merchant_product_form(request2)
        finally:
            _current_store.reset(token2)
            set_urlconf(original_urlconf)

        self.assertEqual(
            response2.status_code, 200,
            f"Expected 200 (form rendered) after limit override, got {response2.status_code}"
        ) # Form page loads successfully
