from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from apps.providers.models import (
    ProviderProfile, ProviderProduct, ProviderMapping, ProviderPrice,
    ProviderOrder, ProviderOrderStatus, ProviderSyncLog
)
from apps.catalog.models import Product, ProductVariant, Category
from apps.orders.models import Order
from services.provider.alkasr.client import AlkasrAPIClient
from services.provider.alkasr.sync import AlkasrSyncService
from services.provider.alkasr.mapper import AlkasrMapperService
from services.provider.alkasr.order import AlkasrOrderService
from services.provider.alkasr.reconciliation import AlkasrReconciliationService


class AlkasrCompleteOverhaulTests(TestCase):
    """
    Comprehensive Test Suite for Phases 4 to 11 of the Alkasr VIP Provider Integration Overhaul.
    """

    def setUp(self):
        self.profile = ProviderProfile.objects.create(
            provider_name="الكاسر VIP",
            api_token="test-secret-token",
            base_url="https://api.alkasr-vip.com/client/api/",
            is_active=True,
            default_retail_margin=Decimal("20.00"),
            default_dealer_margin=Decimal("10.00"),
            default_vip_margin=Decimal("5.00"),
            default_margin_type="percentage"
        )
        self.client = AlkasrAPIClient(api_token="test-secret-token", profile=self.profile)

    # ── PHASE 4: EMPTY RESPONSE SAFETY ──────────────────────────────────────
    def test_empty_response_safety_does_not_deactivate_catalog(self):
        """When provider API returns an empty list, sync aborts safely and keeps existing catalog active."""
        # Setup existing active product
        existing_pp = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="101",
            name="Existing Product",
            is_active=True,
            local_is_active=True,
            cost_price=Decimal("10.00")
        )
        existing_prod = Product.objects.create(
            name="Existing Product",
            api_provider="alkasr",
            api_product_id=101,
            is_active=True,
            is_out_of_stock=False
        )

        sync_service = AlkasrSyncService(self.client, self.profile)

        # Mock API returning empty list
        with patch.object(self.client, "get_products", return_value=[]):
            res = sync_service.sync_catalog()

        self.assertEqual(res.get("status"), "aborted")

        # Verify existing product was NOT deactivated or deleted
        existing_pp.refresh_from_db()
        existing_prod.refresh_from_db()
        self.assertTrue(existing_pp.is_active)
        self.assertTrue(existing_prod.is_active)
        self.assertFalse(existing_prod.is_out_of_stock)

        # Verify sync log records failure/abort safely
        log = ProviderSyncLog.objects.filter(profile=self.profile).last()
        self.assertEqual(log.status, "failed")
        self.assertIn("aborted safely", log.error_message)

    # ── PHASE 4 & 6: PRODUCT & PACKAGE SYNCHRONIZATION ───────────────────────
    def test_canonical_root_and_package_sync(self):
        """
        Root products (parent_id=0) map to Product.
        Packages (parent_id>0) map strictly to ProductVariant linked to the parent Product.
        Zero fuzzy matching or arbitrary grouping.
        """
        api_payload = [
            {
                "id": 10,
                "parent_id": 0,
                "name": "PUBG Mobile UC",
                "category_name": "ألعاب",
                "product_type": "package",
                "available": True,
                "price": "0.00",
                "base_price": "0.00",
                "qty_values": None,
                "params": [{"name": "playerId", "label": "معرف اللاعب", "type": "text", "required": True}],
                "category_img": "https://example.com/pubg.png"
            },
            {
                "id": 1001,
                "parent_id": 10,
                "name": "60 شدة ببجي",
                "category_name": "ألعاب",
                "product_type": "package",
                "available": True,
                "price": "0.95",
                "base_price": "0.95",
                "qty_values": None,
                "params": [{"name": "playerId", "label": "معرف اللاعب", "type": "text", "required": True}]
            },
            {
                "id": 20,
                "parent_id": 0,
                "name": "Free Fire Diamonds",
                "category_name": "ألعاب",
                "product_type": "package",
                "available": True,
                "price": "0.00",
                "base_price": "0.00",
                "qty_values": None,
                "params": [{"name": "playerId", "label": "معرف اللاعب", "type": "text", "required": True}]
            },
            {
                "id": 2001,
                "parent_id": 20,
                "name": "100 جوهرة فري فاير",
                "category_name": "ألعاب",
                "product_type": "package",
                "available": True,
                "price": "1.00",
                "base_price": "1.00",
                "qty_values": None,
                "params": [{"name": "playerId", "label": "معرف اللاعب", "type": "text", "required": True}]
            }
        ]

        sync_service = AlkasrSyncService(self.client, self.profile)
        with patch.object(self.client, "get_products", return_value=api_payload):
            with patch.object(self.client, "get_content", return_value=[]):
                res = sync_service.sync_catalog()

        self.assertEqual(res.get("status"), "completed")

        # Verify Root Products in catalog
        pubg_prod = Product.objects.filter(api_product_id=10, api_provider="alkasr").first()
        self.assertIsNotNone(pubg_prod)
        self.assertEqual(pubg_prod.name, "PUBG Mobile UC")
        self.assertTrue(pubg_prod.is_active)

        ff_prod = Product.objects.filter(api_product_id=20, api_provider="alkasr").first()
        self.assertIsNotNone(ff_prod)
        self.assertEqual(ff_prod.name, "Free Fire Diamonds")

        # Verify Packages linked STRICTLY to their true parent
        pubg_var = ProductVariant.objects.filter(api_product_id=1001).first()
        self.assertIsNotNone(pubg_var)
        self.assertEqual(pubg_var.product_id, pubg_prod.id)
        self.assertEqual(pubg_var.provider_parent_id, 10)
        self.assertEqual(pubg_var.name, "60 شدة ببجي")
        self.assertEqual(pubg_var.cost, Decimal("0.95"))
        # Price: 0.95 + 20% = 1.14
        self.assertAlmostEqual(float(pubg_var.price), 1.14, places=2)

        ff_var = ProductVariant.objects.filter(api_product_id=2001).first()
        self.assertIsNotNone(ff_var)
        self.assertEqual(ff_var.product_id, ff_prod.id)
        self.assertEqual(ff_var.provider_parent_id, 20)
        self.assertEqual(ff_var.name, "100 جوهرة فري فاير")
        # Ensure Free Fire diamond is NEVER attached to PUBG
        self.assertNotEqual(ff_var.product_id, pubg_prod.id)

    # ── PHASE 5: STALE PRODUCTS SOFT DEACTIVATION ────────────────────────────
    def test_stale_products_soft_deactivation(self):
        """Products absent from provider response are deactivated without deletion."""
        # Create an existing product with variant
        pp_old = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="999",
            remote_parent_id="90",
            name="Discontinued Item",
            is_active=True,
            local_is_active=True,
            cost_price=Decimal("5.00")
        )
        parent_prod = Product.objects.create(
            name="Old Parent",
            api_provider="alkasr",
            api_product_id=90,
            is_active=True
        )
        old_var = ProductVariant.objects.create(
            product=parent_prod,
            name="Discontinued Item",
            sku=f"PRV-{self.profile.id}-999",
            api_product_id=999,
            provider_parent_id=90,
            cost=Decimal("5.00"),
            price=Decimal("6.00"),
            is_active=True
        )

        # Sync new list that does NOT include 999
        api_payload = [
            {
                "id": 90,
                "parent_id": 0,
                "name": "Old Parent",
                "category_name": "عام",
                "product_type": "package",
                "available": True,
                "price": "0.00",
                "qty_values": None
            }
        ]

        sync_service = AlkasrSyncService(self.client, self.profile)
        with patch.object(self.client, "get_products", return_value=api_payload):
            with patch.object(self.client, "get_content", return_value=[]):
                sync_service.sync_catalog()

        # ProviderProduct 999 must be soft-disabled
        pp_old.refresh_from_db()
        self.assertFalse(pp_old.is_active)
        self.assertEqual(pp_old.sync_status, "stale")

        # Variant 999 must be soft-disabled
        old_var.refresh_from_db()
        self.assertFalse(old_var.is_active)
        self.assertTrue(old_var.is_temporarily_disabled)

        # Record still exists (never deleted)
        self.assertTrue(ProviderProduct.objects.filter(remote_id="999").exists())

    # ── PHASE 6: CLEANUP CORRUPTED MAPPINGS ──────────────────────────────────
    def test_cleanup_corrupted_mappings_reassigns_variant(self):
        """Cleanup utility identifies variants attached to wrong product and reassigns them."""
        wrong_prod = Product.objects.create(name="Wrong Product", api_provider="alkasr", api_product_id=500)
        correct_prod = Product.objects.create(name="Correct Product", api_provider="alkasr", api_product_id=600)

        # Variant misassigned to wrong_prod
        var = ProductVariant.objects.create(
            product=wrong_prod,
            name="Mismatched Variant",
            sku=f"PRV-{self.profile.id}-7777",
            api_product_id=7777,
            provider_parent_id=600,  # real parent is 600
            price=Decimal("10.00"),
            cost=Decimal("8.00"),
            is_active=True
        )

        res = AlkasrMapperService.cleanup_corrupted_mappings(self.profile)
        self.assertEqual(res["reassigned_count"], 1)

        var.refresh_from_db()
        self.assertEqual(var.product_id, correct_prod.id)

    # ── PHASE 7: ORDER CREATION & IDEMPOTENCY ────────────────────────────────
    def test_order_submission_strict_idempotency(self):
        """Retrying an order with the same order_uuid never generates a new UUID or duplicate submission."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="order_test_user", defaults={"email": "order_test@example.com"})
        local_order = Order.objects.create(customer=user, total_amount=Decimal("2.00"), status=Order.Status.PROCESSING)

        pp = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="555",
            name="Test Game Item",
            is_active=True,
            cost_price=Decimal("2.00")
        )

        order_service = AlkasrOrderService(self.client, self.profile)
        fixed_uuid = "11111111-2222-3333-4444-555555555555"

        with patch.object(self.client, "create_order", return_value={"id": 88001, "status": "processing"}) as mock_create:
            first_res = order_service.submit_order(
                local_order=local_order,
                provider_product=pp,
                quantity=1,
                player_params={"playerId": "987654"},
                order_uuid=fixed_uuid
            )
            mock_create.assert_called_once()
            self.assertEqual(str(first_res["remote_order_id"]), "88001")
            self.assertEqual(first_res["uuid"], fixed_uuid)

        # Second submission with the SAME order_uuid
        with patch.object(self.client, "create_order") as mock_create_second:
            second_res = order_service.submit_order(
                local_order=local_order,
                provider_product=pp,
                quantity=1,
                player_params={"playerId": "987654"},
                order_uuid=fixed_uuid
            )
            # Must NOT call API again
            mock_create_second.assert_not_called()
            # Returns existing order
            self.assertEqual(str(second_res["remote_order_id"]), "88001")
            self.assertEqual(second_res["uuid"], fixed_uuid)

    # ── PHASE 8: ORDER STATUS MAPPING ────────────────────────────────────────
    def test_order_status_mapping_exact(self):
        """0->pending, 1->processing, 2->completed, 3->failed, 4->failed."""
        from services.provider.alkasr.constants import PROVIDER_STATUS_MAP

        self.assertEqual(PROVIDER_STATUS_MAP[0], "pending")
        self.assertEqual(PROVIDER_STATUS_MAP["0"], "pending")
        self.assertEqual(PROVIDER_STATUS_MAP[1], "processing")
        self.assertEqual(PROVIDER_STATUS_MAP["1"], "processing")
        self.assertEqual(PROVIDER_STATUS_MAP[2], "completed")
        self.assertEqual(PROVIDER_STATUS_MAP["2"], "completed")
        self.assertEqual(PROVIDER_STATUS_MAP[3], "failed")
        self.assertEqual(PROVIDER_STATUS_MAP["3"], "failed")
        self.assertEqual(PROVIDER_STATUS_MAP[4], "failed")
        self.assertEqual(PROVIDER_STATUS_MAP["4"], "failed")

    # ── PHASE 9: ORDER RECONCILIATION ────────────────────────────────────────
    def test_order_reconciliation_batch(self):
        """Reconciliation audits pending orders and updates ProviderOrder and local Order."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="rec_test_user", defaults={"email": "rec_test@example.com"})
        local_order = Order.objects.create(customer=user, total_amount=Decimal("2.00"), status=Order.Status.PROCESSING)

        pp = ProviderProduct.objects.create(
            profile=self.profile,
            remote_id="666",
            name="Item 666",
            cost_price=Decimal("1.00")
        )
        po1 = ProviderOrder.objects.create(
            profile=self.profile,
            local_order=local_order,
            uuid="33333333-3333-3333-3333-333333333331",
            remote_order_id="9901",
            product=pp,
            status="pending",
            cost=Decimal("1.00")
        )
        po2 = ProviderOrder.objects.create(
            profile=self.profile,
            local_order=local_order,
            uuid="33333333-3333-3333-3333-333333333332",
            remote_order_id="9902",
            product=pp,
            status="processing",
            cost=Decimal("1.00")
        )

        mock_api_check = [
            {"order_id": 9901, "status": "2", "msg": "Completed successfully"},
            {"order_id": 9902, "status": "3", "msg": "Rejected by server"}
        ]

        rec_service = AlkasrReconciliationService(self.profile, self.client)
        with patch.object(self.client, "check_orders", return_value=mock_api_check):
            stats = rec_service.reconcile_pending_orders(days=7)

        self.assertEqual(stats["checked"], 2)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["failed"], 1)

        po1.refresh_from_db()
        po2.refresh_from_db()
        self.assertEqual(po1.status, "completed")
        self.assertEqual(po2.status, "failed")

        # Verify status history recorded
        self.assertTrue(ProviderOrderStatus.objects.filter(provider_order=po1, status="completed").exists())
        self.assertTrue(ProviderOrderStatus.objects.filter(provider_order=po2, status="failed").exists())
