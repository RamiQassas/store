from django.test import TestCase, Client
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
