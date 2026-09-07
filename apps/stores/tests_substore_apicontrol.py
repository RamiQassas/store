import uuid
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from apps.stores.models import Store, SubscriptionPlan, StoreEmployee
from apps.catalog.models import Product, Category, ProductVariant, APIIntegration, ProductKey
from apps.wallets.models import Wallet
from apps.wallets.services import get_or_create_wallet
from apps.common.models import Currency
from apps.common.tenant_utils import set_current_store, bypass_tenant_filter, _current_store
from apps.site.views import control_api_integrations_list, control_apicontrol_dashboard, control_api_integration_delete
from apps.orders.services import create_order
from apps.orders.models import Order

from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware

User = get_user_model()


class SubStoreAPIControlTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        # Currency
        self.currency = Currency.objects.create(
            name="US Dollar",
            code="USD",
            symbol="$",
            buy_rate=1.0,
            sell_rate=1.0,
            is_default=True
        )

        self.free_plan = SubscriptionPlan.objects.create(
            name="Free Plan",
            max_products=50,
            max_employees=5,
            max_monthly_orders=100,
            is_active=True
        )

        with bypass_tenant_filter():
            self.owner_a = User.objects.create_user(
                email="merchant_a@example.com",
                password="Password123!",
                role="store_owner"
            )
            self.owner_b = User.objects.create_user(
                email="merchant_b@example.com",
                password="Password123!",
                role="store_owner"
            )
            self.customer_a = User.objects.create_user(
                email="customer_a@example.com",
                password="Password123!",
                role="customer"
            )

        self.store_a = Store.objects.create(
            owner=self.owner_a,
            name="Store A",
            subdomain="store-a",
            subscription_plan=self.free_plan,
            tier_margins={"customer": 20.0, "dealer": 10.0, "vip": 5.0},
            is_active=True
        )
        StoreEmployee.objects.create(store=self.store_a, user=self.owner_a, role="owner")

        self.store_b = Store.objects.create(
            owner=self.owner_b,
            name="Store B",
            subdomain="store-b",
            subscription_plan=self.free_plan,
            is_active=True
        )
        StoreEmployee.objects.create(store=self.store_b, user=self.owner_b, role="owner")

        # Global Products on Raqamiyat Platform (store=None)
        with bypass_tenant_filter():
            self.global_cat = Category.objects.create(name="Gaming Cards", store=None, is_active=True)
            self.global_prod = Product.objects.create(
                name="PUBG Mobile 60 UC",
                category=self.global_cat,
                store=None,
                is_active=True,
                is_api_product=True,
                api_provider="raqamiyat"
            )
            self.global_var = ProductVariant.objects.create(
                product=self.global_prod,
                name="60 UC",
                sku="PUBG-60-UC",
                cost=Decimal("1.00"),
                price=Decimal("1.20"),
                delivery_type="keys",
                is_active=True
            )
            # Create a global digital key for this variant
            self.global_key = ProductKey.objects.create(
                variant=self.global_var,
                key_code="GLOBAL-PUBG-KEY-12345",
                is_used=False
            )

    def _setup_request(self, request, user, store=None):
        request.user = user
        request.store = store
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        from django.urls import set_urlconf
        if store:
            request.urlconf = 'apps.stores.urls'
            set_urlconf('apps.stores.urls')
        else:
            request.urlconf = 'config.urls'
            set_urlconf('config.urls')

    def tearDown(self):
        from django.urls import set_urlconf
        set_urlconf(None)

    def test_default_raqamiyat_integration_auto_provisioning_and_isolation(self):
        """Verify Raqamiyat default provider is created for sub-store and strictly tenant-isolated."""
        # 1. Store A visits integrations list
        request_a = self.factory.get("/merchant/api-integrations/")
        self._setup_request(request_a, self.owner_a, self.store_a)
        token_a = set_current_store(self.store_a)
        try:
            response_a = control_api_integrations_list(request_a)
            self.assertEqual(response_a.status_code, 200)

            # Store A should now have Raqamiyat integration
            integ_a = APIIntegration.objects.filter(store=self.store_a, provider="raqamiyat").first()
            self.assertIsNotNone(integ_a)
            self.assertEqual(integ_a.name, "رقميات (المتجر الأساسي)")
            self.assertEqual(integ_a.store, self.store_a)
        finally:
            _current_store.reset(token_a)

        # 2. Store B visits integrations list
        request_b = self.factory.get("/merchant/api-integrations/")
        self._setup_request(request_b, self.owner_b, self.store_b)
        token_b = set_current_store(self.store_b)
        try:
            response_b = control_api_integrations_list(request_b)
            self.assertEqual(response_b.status_code, 200)

            integ_b = APIIntegration.objects.filter(store=self.store_b, provider="raqamiyat").first()
            self.assertIsNotNone(integ_b)
            self.assertNotEqual(integ_a.id, integ_b.id)

            # Store B can only see its own integrations!
            store_b_integrations = list(APIIntegration.objects.filter(store=self.store_b))
            self.assertIn(integ_b, store_b_integrations)
            self.assertNotIn(integ_a, store_b_integrations)
        finally:
            _current_store.reset(token_b)

        # 3. Verify deletion of Raqamiyat provider is blocked
        delete_request = self.factory.post(f"/merchant/api-integrations/{integ_a.pk}/delete/")
        self._setup_request(delete_request, self.owner_a, self.store_a)
        token_a = set_current_store(self.store_a)
        try:
            del_resp = control_api_integration_delete(delete_request, integ_a.pk)
            # Integration still exists!
            self.assertTrue(APIIntegration.objects.filter(pk=integ_a.pk).exists())
        finally:
            _current_store.reset(token_a)

    def test_substore_apicontrol_dashboard_margins_and_price_sync(self):
        """Verify sub-store merchant can control profit margins and recalculate catalog prices."""
        # Top up owner A's wallet on Raqamiyat platform (store=None)
        with bypass_tenant_filter():
            owner_wallet = Wallet.all_objects.filter(user=self.owner_a, store__isnull=True).first()
            if not owner_wallet:
                owner_wallet = Wallet.all_objects.create(
                    user=self.owner_a,
                    store=None,
                    currency=self.currency,
                    available_balance=Decimal("50.00")
                )
            else:
                owner_wallet.available_balance = Decimal("50.00")
                owner_wallet.save(update_fields=["available_balance"])

        request = self.factory.get("/merchant/apicontrol/")
        self._setup_request(request, self.owner_a, self.store_a)
        token_a = set_current_store(self.store_a)
        try:
            response = control_apicontrol_dashboard(request)
            self.assertEqual(response.status_code, 200)

            # Check rendered content: live balance from Raqamiyat wallet and provider name
            content_str = response.content.decode("utf-8")
            self.assertIn("رقميات (المتجر الأساسي)", content_str)
            self.assertTrue("50,0" in content_str or "50.0" in content_str or "50" in content_str)

            # Now test updating margins via POST action="update_margins"
            post_req = self.factory.post("/merchant/apicontrol/", {
                "action": "update_margins",
                "retail_margin": "30.0",
                "dealer_margin": "15.0",
                "vip_margin": "8.0",
            })
            self._setup_request(post_req, self.owner_a, self.store_a)
            post_resp = control_apicontrol_dashboard(post_req)
            self.assertEqual(post_resp.status_code, 302)

            # Verify store margins updated
            self.store_a.refresh_from_db()
            self.assertEqual(self.store_a.tier_margins["customer"], 30.0)
            self.assertEqual(self.store_a.tier_margins["dealer"], 15.0)
            self.assertEqual(self.store_a.tier_margins["vip"], 8.0)

            # Verify product variant prices imported and recalculated in Store A
            store_var = ProductVariant.objects.filter(product__store=self.store_a, name="60 UC").first()
            self.assertIsNotNone(store_var)
            # Base cost is 1.00, customer margin 30% -> price should be 1.30
            self.assertEqual(store_var.cost, Decimal("1.00"))
            self.assertEqual(store_var.price, Decimal("1.30"))
            self.assertEqual(store_var.wholesale_price, Decimal("1.15"))
            self.assertEqual(store_var.vip_price, Decimal("1.08"))
        finally:
            _current_store.reset(token_a)

    def test_substore_order_wholesale_cost_auto_deduction_and_insufficient_balance(self):
        """Verify wholesale cost auto-debit from merchant's Raqamiyat wallet and rejection if insufficient."""
        from apps.stores.services import import_raqamiyat_products_for_store
        import_raqamiyat_products_for_store(self.store_a)

        store_var = ProductVariant.objects.filter(product__store=self.store_a, name="60 UC").first()
        self.assertIsNotNone(store_var)

        # Merchant A has 0.00 in Raqamiyat platform wallet
        with bypass_tenant_filter():
            owner_wallet = Wallet.all_objects.filter(user=self.owner_a, store__isnull=True).first()
            if not owner_wallet:
                owner_wallet = Wallet.all_objects.create(
                    user=self.owner_a,
                    store=None,
                    currency=self.currency,
                    available_balance=Decimal("0.00")
                )
            else:
                owner_wallet.available_balance = Decimal("0.00")
                owner_wallet.save(update_fields=["available_balance"])

        token_a = set_current_store(self.store_a)
        try:
            # Customer A has balance in Store A
            cust_wallet = get_or_create_wallet(self.customer_a)
            cust_wallet.available_balance = Decimal("100.00")
            cust_wallet.save(update_fields=["available_balance"])

            # 1. Order should FAIL with friendly message without exposing store owner balance
            with self.assertRaises(ValueError) as ctx_err:
                create_order(
                    customer=self.customer_a,
                    variant_id=store_var.id,
                    quantity=1
                )
            self.assertIn("لم يتم إكمال الطلب، يرجى التواصل مع دعم المتجر", str(ctx_err.exception))

            # Verify store owner received an alert notification
            from apps.notifications.models import Notification
            notif = Notification.objects.filter(user=self.store_a.owner).first()
            self.assertIsNotNone(notif)
            self.assertIn("رصيد الجملة في رقميات غير كافٍ", notif.title)

            # 2. Now top up merchant A's Raqamiyat platform wallet with 10.00 USD
            with bypass_tenant_filter():
                owner_wallet.available_balance = Decimal("10.00")
                owner_wallet.save(update_fields=["available_balance"])

            # 3. Order should SUCCEED and debit wholesale cost (1.00 USD) from owner_wallet
            order = create_order(
                customer=self.customer_a,
                variant_id=store_var.id,
                quantity=1
            )
            self.assertIsNotNone(order)
            self.assertEqual(order.status, Order.Status.COMPLETED)

            # Check that digital key was delivered from global keys!
            self.assertIn("keys", order.fulfillment_data)
            self.assertEqual(order.fulfillment_data["keys"], ["GLOBAL-PUBG-KEY-12345"])

            # Check owner's Raqamiyat platform wallet balance: 10.00 - 1.00 = 9.00
            owner_wallet.refresh_from_db()
            self.assertEqual(owner_wallet.available_balance, Decimal("9.00"))

            # Check customer's wallet balance: 100.00 - store_var.price (1.20) = 98.80
            cust_wallet.refresh_from_db()
            self.assertEqual(cust_wallet.available_balance, Decimal("100.00") - store_var.price)
        finally:
            _current_store.reset(token_a)

    def test_substore_raqamiyat_interactive_sync_and_progress_polling(self):
        """Verify AJAX sync start, background progress tracking, and polling for Raqamiyat sub-store."""
        import json
        from apps.stores.services import import_raqamiyat_products_for_store

        # 1. Test import_raqamiyat_products_for_store directly with callback
        progress_records = []
        def on_prog(cur, tot, name, cr, up):
            progress_records.append((cur, tot, name))

        stats = import_raqamiyat_products_for_store(self.store_a, progress_callback=on_prog)
        self.assertGreater(len(progress_records), 0)
        self.assertEqual(progress_records[-1][0], progress_records[-1][1])  # cur == tot
        self.assertIn("PUBG", progress_records[-1][2])

        # 2. Test AJAX POST to /merchant/apicontrol/ with action="sync_ajax"
        integ_a = APIIntegration.objects.filter(store=self.store_a, provider="raqamiyat").first()
        if not integ_a:
            integ_a = APIIntegration.objects.create(
                store=self.store_a,
                provider="raqamiyat",
                name="رقميات (المتجر الأساسي)",
                is_active=True
            )

        post_req = self.factory.post("/merchant/apicontrol/", {
            "action": "sync_ajax",
            "integration_id": str(integ_a.id),
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self._setup_request(post_req, self.owner_a, self.store_a)
        token_a = set_current_store(self.store_a)
        try:
            resp = control_apicontrol_dashboard(post_req)
            self.assertEqual(resp.status_code, 200)
            data = json.loads(resp.content)
            self.assertIn(data.get("status"), ["started", "completed"])

            # 3. Test GET progress endpoint
            get_req = self.factory.get(f"/merchant/apicontrol/?action=get_sync_progress&sync_progress=1&integration_id={integ_a.id}", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self._setup_request(get_req, self.owner_a, self.store_a)
            get_resp = control_apicontrol_dashboard(get_req)
            self.assertEqual(get_resp.status_code, 200)
            prog_data = json.loads(get_resp.content)
            self.assertIn(prog_data.get("status"), ["running", "completed", "idle"])

            # Wait briefly for background thread to finish cleanly before test teardown
            import time
            time.sleep(0.5)
        finally:
            _current_store.reset(token_a)

    def test_substore_currency_isolation_and_context_processor(self):
        """Verify currencies and exchange rates are isolated per sub-store and auto-provisioned."""
        from apps.common.models import Currency
        from apps.site.context_processors import preferred_currency

        # Ensure Store A has no currencies initially
        Currency.all_objects.filter(store=self.store_a).delete()
        self.assertEqual(Currency.all_objects.filter(store=self.store_a).count(), 0)

        # Call preferred_currency context processor for Store A request
        req = self.factory.get("/")
        self._setup_request(req, self.customer_a, self.store_a)
        ctx = preferred_currency(req)

        # 1. Currencies should be auto-provisioned for Store A
        store_a_currencies = Currency.all_objects.filter(store=self.store_a)
        self.assertGreater(store_a_currencies.count(), 0)
        self.assertIsNotNone(ctx.get("CURRENCY"))
        self.assertEqual(ctx["CURRENCY"].store, self.store_a)

        # 2. Modify exchange rate in Store A: SYP buy rate = 15500
        syp_a = store_a_currencies.filter(code="SYP").first()
        if syp_a:
            syp_a.buy_rate = Decimal("15500.00")
            syp_a.save()

            # Global SYP rate must remain unaffected
            global_syp = Currency.all_objects.filter(store__isnull=True, code="SYP").first()
            if global_syp:
                self.assertNotEqual(global_syp.buy_rate, Decimal("15500.00"))

        # 3. Test Currency.save is_default scoping to store
        usd_a = store_a_currencies.filter(code="USD").first()
        if usd_a and syp_a:
            syp_a.is_default = True
            syp_a.save()
            usd_a.refresh_from_db()
            self.assertFalse(usd_a.is_default)

            # Global default currency should NOT be affected
            global_def = Currency.all_objects.filter(store__isnull=True, is_default=True).first()
            if global_def:
                self.assertTrue(global_def.is_default)

    def test_control_users_list_store_filtering_and_isolation(self):
        """Verify /control/users/ isolates platform users by default and shows all on toggle."""
        from apps.site.views import control_users_list

        admin_user = User.objects.create_user(
            email="platform_admin@example.com",
            password="Password123!",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        store_customer = User.objects.create_user(
            email="store_customer_unique@example.com",
            password="Password123!",
            role=User.Role.CUSTOMER,
            store=self.store_a,
        )

        # Admin request without all_stores: should ONLY show platform users (store__isnull=True)
        req_default = self.factory.get("/control/users/")
        self._setup_request(req_default, admin_user, None)
        resp_default = control_users_list(req_default)
        self.assertEqual(resp_default.status_code, 200)
        content_default = resp_default.content.decode("utf-8")
        self.assertNotIn(store_customer.email, content_default)
        self.assertIn("إظهار جميع حسابات المتاجر", content_default)

        # Admin request with all_stores=1: should show ALL users across all stores
        req_all = self.factory.get("/control/users/?all_stores=1")
        self._setup_request(req_all, admin_user, None)
        resp_all = control_users_list(req_all)
        self.assertEqual(resp_all.status_code, 200)
        content_all = resp_all.content.decode("utf-8")
        self.assertIn(store_customer.email, content_all)
        self.assertIn(self.store_a.name, content_all)
        self.assertIn("إظهار حسابات رقميات فقط", content_all)

        # Admin request filtered by store_id=store_a.id: should show Store A users
        req_store_a = self.factory.get(f"/control/users/?all_stores=1&store_id={self.store_a.id}")
        self._setup_request(req_store_a, admin_user, None)
        resp_store_a = control_users_list(req_store_a)
        self.assertEqual(resp_store_a.status_code, 200)
        content_store_a = resp_store_a.content.decode("utf-8")
        self.assertIn(store_customer.email, content_store_a)
        self.assertIn(self.store_a.name, content_store_a)



