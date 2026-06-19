from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.wallets.models import Wallet, LedgerEntry, RechargeCard, BalanceTransfer
from apps.common.models import Currency
from apps.catalog.models import Product, Category, ProductVariant
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.wallets.services import get_or_create_wallet, credit_wallet
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tests",
    }
}

@override_settings(SECURE_SSL_REDIRECT=False, CACHES=TEST_CACHES)
class RechargeCardTests(TestCase):
    def setUp(self):
        # Ensure currencies are present
        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "buy_rate": 1.0, "sell_rate": 1.0, "is_default": True}
        )
        self.try_curr, _ = Currency.objects.get_or_create(
            code="TRY",
            defaults={"name": "Turkish Lira", "symbol": "TL", "buy_rate": 32.0, "sell_rate": 32.0, "conversion_method": "multiply"}
        )
        
        self.user = User.objects.create_user(email="buyer@example.com", password="StrongPass12345")
        self.wallet = get_or_create_wallet(self.user)
        
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_recharge_card_redemption_success_same_currency(self):
        card = RechargeCard.objects.create(
            code="RC-TEST-USD-11",
            amount=Decimal("50.00"),
            currency=self.usd,
            status=RechargeCard.Status.ACTIVE
        )
        
        response = self.client.post(reverse("dashboard_recharge_wallet"), {"recharge_code": "RC-TEST-USD-11"})
        self.assertEqual(response.status_code, 302) # Redirects back to wallet
        
        # Verify wallet balance
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("50.00"))
        
        # Verify card status
        card.refresh_from_db()
        self.assertEqual(card.status, RechargeCard.Status.REDEEMED)
        self.assertEqual(card.redeemed_by, self.user)
        self.assertIsNotNone(card.redeemed_at)
        
        # Verify Ledger Entry
        entry = LedgerEntry.objects.filter(wallet=self.wallet).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.entry_type, LedgerEntry.EntryType.CREDIT)
        self.assertEqual(entry.amount, Decimal("50.00"))

    def test_recharge_card_redemption_with_conversion(self):
        # Wallet is in USD, card is 320.00 TRY. Conversion is 320 / 32 = 10.00 USD.
        card = RechargeCard.objects.create(
            code="RC-TEST-TRY-22",
            amount=Decimal("320.00"),
            currency=self.try_curr,
            status=RechargeCard.Status.ACTIVE
        )
        
        response = self.client.post(reverse("dashboard_recharge_wallet"), {"recharge_code": "RC-TEST-TRY-22"})
        self.assertEqual(response.status_code, 302)
        
        # Verify wallet balance is 10.00 USD
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("10.00"))
        
        # Verify Ledger Entry metadata
        entry = LedgerEntry.objects.filter(wallet=self.wallet).first()
        self.assertEqual(entry.metadata["source_amount"], "320.00")
        self.assertEqual(entry.metadata["source_currency"], "TRY")

    def test_recharge_card_already_used_or_invalid(self):
        card = RechargeCard.objects.create(
            code="RC-USED",
            amount=Decimal("20.00"),
            currency=self.usd,
            status=RechargeCard.Status.REDEEMED,
            redeemed_by=self.user,
            redeemed_at=timezone.now()
        )
        
        response = self.client.post(reverse("dashboard_recharge_wallet"), {"recharge_code": "RC-USED"})
        self.assertEqual(response.status_code, 302)
        
        # Wallet should not change
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("0.00"))
        
        response2 = self.client.post(reverse("dashboard_recharge_wallet"), {"recharge_code": "RC-NONEXISTENT"})
        self.assertEqual(response2.status_code, 302)

    def test_order_completion_auto_fulfillment(self):
        category = Category.objects.create(name="بطاقات شحن", is_active=True)
        product = Product.objects.create(name="بطاقة شحن 25$", category=category, is_active=True)
        variant = ProductVariant.objects.create(
            product=product,
            name="افتراضي",
            sku="RC-V-25",
            price=Decimal("25.00"),
            is_active=True,
            is_recharge_card=True,
            recharge_amount=Decimal("25.00"),
            recharge_currency=self.usd
        )
        
        # Add funds to user wallet to purchase
        credit_wallet(self.wallet.id, Decimal("50.00"), "test_credit", "Fund user for purchase")
        
        # Purchase product
        order = create_order(customer=self.user, variant_id=variant.id, quantity=1)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        
        # Verify no card created yet
        self.assertFalse(RechargeCard.objects.filter(order=order).exists())
        
        # Complete order
        order.status = Order.Status.COMPLETED
        order.save()
        
        # Verify card is created automatically
        self.assertTrue(RechargeCard.objects.filter(order=order).exists())
        card = RechargeCard.objects.filter(order=order).first()
        self.assertEqual(card.amount, Decimal("25.00"))
        self.assertEqual(card.currency, self.usd)
        self.assertEqual(card.status, RechargeCard.Status.ACTIVE)
        
        # Verify order fulfillment_data
        order.refresh_from_db()
        self.assertIn("أكواد الشحن", order.fulfillment_data)
        self.assertEqual(order.fulfillment_data["أكواد الشحن"], card.code)


class RechargeCardAdminTests(TestCase):
    def setUp(self):
        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "buy_rate": 1.0, "sell_rate": 1.0, "is_default": True}
        )
        self.admin_user = User.objects.create_superuser(email="admin@example.com", password="AdminPass12345")
        self.client = APIClient()
        self.client.force_login(self.admin_user)
        
        # Create some variants for linking
        category = Category.objects.create(name="Digital Keys", is_active=True)
        self.product = Product.objects.create(name="Premium Product", category=category, is_active=True)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="1 Month Key",
            sku="KEY-1M",
            price=Decimal("10.00"),
            is_active=True,
            delivery_type="keys"
        )

    def test_control_recharge_cards_list_filtering_and_sorting(self):
        # Create multiple cards with different amounts, statuses, and creation times
        card1 = RechargeCard.objects.create(
            code="RC-AAAA-1111", amount=Decimal("15.00"), currency=self.usd, status=RechargeCard.Status.ACTIVE
        )
        card2 = RechargeCard.objects.create(
            code="RC-BBBB-2222", amount=Decimal("25.00"), currency=self.usd, status=RechargeCard.Status.REDEEMED
        )
        
        # Test basic list
        url = reverse("control_recharge_cards")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RC-AAAA-1111")
        self.assertContains(response, "RC-BBBB-2222")

        # Test filtering by status
        response_active = self.client.get(url, {"status": "active"})
        self.assertContains(response_active, "RC-AAAA-1111")
        self.assertNotContains(response_active, "RC-BBBB-2222")

        # Test filtering by amount
        response_amount = self.client.get(url, {"amount": "25.00"})
        self.assertNotContains(response_amount, "RC-AAAA-1111")
        self.assertContains(response_amount, "RC-BBBB-2222")

        # Test filtering by query (q)
        response_q = self.client.get(url, {"q": "RC-AAAA"})
        self.assertContains(response_q, "RC-AAAA-1111")
        self.assertNotContains(response_q, "RC-BBBB-2222")

        # Test sorting
        response_sort = self.client.get(url, {"sort": "amount"})
        cards = list(response_sort.context["page_obj"])
        self.assertEqual(cards[0].code, "RC-AAAA-1111")
        self.assertEqual(cards[1].code, "RC-BBBB-2222")

    def test_control_recharge_cards_generation_with_variant(self):
        url = reverse("control_recharge_cards_generate")
        
        # POST to generate 5 codes of value 20.00 USD, linked to self.variant
        data = {
            "amount": "20.00",
            "currency": self.usd.id,
            "count": "5",
            "variant_id": str(self.variant.id)
        }
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        
        # Check that 5 RechargeCards were created
        self.assertEqual(RechargeCard.objects.filter(amount=Decimal("20.00")).count(), 5)
        
        # Check that 5 ProductKeys were created and linked to self.variant
        from apps.catalog.models import ProductKey
        self.assertEqual(ProductKey.objects.filter(variant=self.variant).count(), 5)
        
        # Verify the codes match exactly
        card_codes = set(RechargeCard.objects.filter(amount=Decimal("20.00")).values_list("code", flat=True))
        key_codes = set(ProductKey.objects.filter(variant=self.variant).values_list("key_code", flat=True))
        self.assertEqual(card_codes, key_codes)


class P2PTransferTests(TestCase):
    def setUp(self):
        self.usd, _ = Currency.objects.get_or_create(
            code="USD",
            defaults={"name": "US Dollar", "symbol": "$", "buy_rate": 1.0, "sell_rate": 1.0, "is_default": True}
        )
        self.sender = User.objects.create_user(email="sender@example.com", password="StrongPass12345")
        self.recipient = User.objects.create_user(email="recipient@example.com", password="StrongPass12345", first_name="Ahmad", last_name="Ali")
        
        self.sender_wallet = get_or_create_wallet(self.sender)
        self.recipient_wallet = get_or_create_wallet(self.recipient)
        
        # Credit sender with enough money
        credit_wallet(self.sender_wallet.id, Decimal("100.00"), "test_credit", "Fund sender")

    def test_p2p_transfer_success(self):
        from apps.wallets.services import execute_p2p_transfer
        
        transfer = execute_p2p_transfer(
            sender=self.sender,
            recipient=self.recipient,
            amount=Decimal("40.00"),
            currency=self.usd
        )
        
        self.assertEqual(transfer.amount, Decimal("40.00"))
        self.assertEqual(transfer.net_amount, Decimal("40.00")) # 0% fee default
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        
        self.assertEqual(self.sender_wallet.available_balance, Decimal("60.00"))
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("40.00"))
        
        # Check Ledger Entries descriptions
        sender_ledger = LedgerEntry.objects.filter(wallet=self.sender_wallet, entry_type=LedgerEntry.EntryType.DEBIT).first()
        recipient_ledger = LedgerEntry.objects.filter(wallet=self.recipient_wallet, entry_type=LedgerEntry.EntryType.CREDIT).first()
        
        self.assertIn("Transfer to Ahmad Ali", sender_ledger.reason)
        self.assertIn("UID: " + self.recipient.uid, sender_ledger.reason)
        self.assertIn("rec***@example.com", sender_ledger.reason)
        
        self.assertIn("Transfer from sen***@example.com", recipient_ledger.reason)
        self.assertIn("UID: " + self.sender.uid, recipient_ledger.reason)
        
        # Check notifications
        from apps.notifications.models import Notification
        self.assertEqual(Notification.objects.filter(user=self.sender).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.recipient).count(), 1)
        
        sender_notif = Notification.objects.filter(user=self.sender).first()
        recipient_notif = Notification.objects.filter(user=self.recipient).first()
        
        self.assertIn("تم توصيل حوالتك", sender_notif.body)
        self.assertIn("Ahmad Ali", sender_notif.body)
        
        self.assertIn("لقد تلقيت حوالة مالية", recipient_notif.body)

    def test_p2p_transfer_daily_limit_cumulative(self):
        from apps.wallets.services import execute_p2p_transfer
        from apps.accounts.models import KYCSettings
        
        settings = KYCSettings.get_settings()
        settings.unverified_transfer_limit = Decimal("50.00")
        settings.save()
        
        # Transfer 30 USD (under limit of 50)
        execute_p2p_transfer(self.sender, self.recipient, Decimal("30.00"), self.usd)
        
        # Another transfer of 15 USD (cumulative is 45, under limit of 50)
        execute_p2p_transfer(self.sender, self.recipient, Decimal("15.00"), self.usd)
        
        # Trying to transfer 10 USD (cumulative would be 55, exceeds limit of 50)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            execute_p2p_transfer(self.sender, self.recipient, Decimal("10.00"), self.usd)

    def test_p2p_transfer_suspend_and_unsuspend(self):
        from apps.wallets.services import execute_p2p_transfer, suspend_p2p_transfer, unsuspend_p2p_transfer
        
        transfer = execute_p2p_transfer(self.sender, self.recipient, Decimal("40.00"), self.usd)
        
        # Suspend transfer
        suspend_p2p_transfer(transfer, admin_user=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, BalanceTransfer.Status.SUSPENDED)
        
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("0.00"))
        self.assertEqual(self.recipient_wallet.held_balance, Decimal("40.00"))
        
        # Unsuspend transfer
        unsuspend_p2p_transfer(transfer, admin_user=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, BalanceTransfer.Status.COMPLETED)
        
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("40.00"))
        self.assertEqual(self.recipient_wallet.held_balance, Decimal("0.00"))

    def test_p2p_transfer_reverse_suspended(self):
        from apps.wallets.services import execute_p2p_transfer, suspend_p2p_transfer, reverse_p2p_transfer
        
        transfer = execute_p2p_transfer(self.sender, self.recipient, Decimal("40.00"), self.usd)
        
        # Suspend first
        suspend_p2p_transfer(transfer, admin_user=self.sender)
        
        # Reverse suspended transfer
        reverse_p2p_transfer(transfer, admin_user=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, BalanceTransfer.Status.REJECTED)
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.available_balance, Decimal("100.00"))
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("0.00"))
        self.assertEqual(self.recipient_wallet.held_balance, Decimal("0.00"))

    def test_p2p_transfer_edit_amount_increase_success(self):
        from apps.wallets.services import execute_p2p_transfer, edit_p2p_transfer_amount
        
        transfer = execute_p2p_transfer(self.sender, self.recipient, Decimal("40.00"), self.usd)
        
        # Increase from 40 to 60 USD (sender must pay 20 more, recipient gets 20 more)
        edit_p2p_transfer_amount(transfer, Decimal("60.00"), admin_user=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.amount, Decimal("60.00"))
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.available_balance, Decimal("40.00"))
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("60.00"))

    def test_p2p_transfer_edit_amount_decrease_success(self):
        from apps.wallets.services import execute_p2p_transfer, edit_p2p_transfer_amount
        
        transfer = execute_p2p_transfer(self.sender, self.recipient, Decimal("40.00"), self.usd)
        
        # Decrease from 40 to 30 USD (sender gets 10 back, recipient pays 10 back)
        edit_p2p_transfer_amount(transfer, Decimal("30.00"), admin_user=self.sender)
        transfer.refresh_from_db()
        self.assertEqual(transfer.amount, Decimal("30.00"))
        
        self.sender_wallet.refresh_from_db()
        self.recipient_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.available_balance, Decimal("70.00"))
        self.assertEqual(self.recipient_wallet.available_balance, Decimal("30.00"))

    def test_p2p_transfer_edit_amount_insufficient_balances(self):
        from apps.wallets.services import execute_p2p_transfer, edit_p2p_transfer_amount, WalletError
        
        transfer = execute_p2p_transfer(self.sender, self.recipient, Decimal("40.00"), self.usd)
        
        # Test 1: Sender insufficient balance on increase
        self.sender_wallet.available_balance = Decimal("5.00")
        self.sender_wallet.save()
        
        with self.assertRaises(WalletError):
            edit_p2p_transfer_amount(transfer, Decimal("70.00"), admin_user=self.sender)
            
        # Test 2: Recipient insufficient balance on decrease
        self.sender_wallet.available_balance = Decimal("100.00") # restore sender
        self.sender_wallet.save()
        self.recipient_wallet.refresh_from_db()
        self.recipient_wallet.available_balance = Decimal("5.00") # decrease recipient
        self.recipient_wallet.save()
        
        with self.assertRaises(WalletError):
            edit_p2p_transfer_amount(transfer, Decimal("30.00"), admin_user=self.sender)

    def test_financial_analytics_debt_aging_and_cash_deposit(self):
        from apps.site.analytics_services import FinancialAnalyticsService
        from apps.wallets.services import add_debt, pay_debt, credit_wallet
        
        # 1. Add debt to recipient
        add_debt(self.recipient_wallet.id, Decimal("50.00"), "debt_ref_1", "Test debt", self.sender)
        
        # 2. Add cash deposit to sender (using source="admin_cash")
        credit_wallet(
            wallet_id=self.sender_wallet.id,
            amount=Decimal("30.00"),
            reference="cash_dep_ref",
            description="Cash deposit",
            created_by=self.sender,
            source="admin_cash"
        )
        
        # 3. Pay some debt in cash (using source="admin_cash")
        pay_debt(
            wallet_id=self.recipient_wallet.id,
            amount=Decimal("15.00"),
            reference="cash_pay_ref",
            reason="Cash payment",
            created_by=self.sender,
            deduct_from_balance=False,
            source="admin_cash"
        )
        
        analytics = FinancialAnalyticsService()
        
        # Check debt aging (should run without AttributeError)
        debt_aging = analytics.get_debt_aging()
        self.assertIsNotNone(debt_aging)
        self.assertIn("1-7", debt_aging)
        self.assertEqual(debt_aging["1-7"]["count"], 1)
        self.assertEqual(debt_aging["1-7"]["amount"], Decimal("35.00")) # 50 - 15 paid
        
        # Check cash collections KPIs
        kpis = analytics.get_dashboard_kpis()
        # total_cash_collections should be cash deposit (30.00) + cash debt payment (15.00) = 45.00
        self.assertEqual(kpis["total_cash_collections"], Decimal("45.00"))
        
        # Check cash collection logs
        cash_logs = list(analytics.get_cash_collection_logs())
        self.assertEqual(len(cash_logs), 2)
