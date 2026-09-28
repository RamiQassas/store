from decimal import Decimal
from django.test import TestCase

from apps.providers.models import ProviderProfile, ProviderCategory, ProviderProduct, ProviderPrice
from apps.catalog.models import Product, ProductVariant
from apps.providers.alkasr.sync import AlkasrSyncService
from apps.providers.alkasr.mapper import AlkasrMapperService


class AlkasrHierarchyAndMappingTestCase(TestCase):
    def setUp(self):
        self.profile = ProviderProfile.objects.create(
            provider_name="Alkasr VIP",
            api_token="dummy_token",
            base_url="https://api.alkasr-vip.com/client/api",
            balance=Decimal("100.00"),
        )
        self.sync_svc = AlkasrSyncService(self.profile)
        self.mapper_svc = AlkasrMapperService(self.profile)

    def test_two_pass_category_sync(self):
        """
        Verify that categories received in arbitrary order (e.g. child before parent)
        have their parent ForeignKeys correctly established via two-pass sync.
        """
        # Child 101 has parent 1, but 101 appears before 1 in dict keys
        content_by_id = {
            "101": [
                {"id": "1001", "name": "Server 1", "parent_id": "101"}
            ],
            "1": [
                {"id": "101", "name": "PUBG Mobile", "parent_id": "1"}
            ],
            "0": [
                {"id": "1", "name": "Games", "parent_id": "0"}
            ]
        }
        cats_by_remote, order_map = self.sync_svc._sync_categories(content_by_id)

        cat_1 = cats_by_remote["1"]
        cat_101 = cats_by_remote["101"]
        cat_1001 = cats_by_remote["1001"]

        self.assertIsNone(cat_1.parent)
        self.assertEqual(cat_101.parent.id, cat_1.id)
        self.assertEqual(cat_1001.parent.id, cat_101.id)

    def test_distinct_soul_apps_never_merged(self):
        """
        Verify that Soul Chill (سوشيل / سول تشيل), Soul Star (سول ستار), and Soul App
        remain completely distinct catalog products and are NOT merged.
        """
        cat_live = ProviderCategory.objects.create(profile=self.profile, remote_id="2", name="شحن التطبيقات")
        
        # 1. Soul Chill
        cat_chill = ProviderCategory.objects.create(profile=self.profile, remote_id="21", name="Soul Chill", parent=cat_live)
        pp_chill = ProviderProduct.objects.create(
            profile=self.profile, remote_id="201", remote_parent_id="21", name="سوشيل 500 جوهرة",
            category=cat_chill, cost_price=Decimal("1.50"), is_active=True, local_is_active=True
        )
        ProviderPrice.objects.create(product=pp_chill, margin_value=Decimal("10.00"))

        # 2. Soul Star
        cat_star = ProviderCategory.objects.create(profile=self.profile, remote_id="22", name="سول ستار", parent=cat_live)
        pp_star = ProviderProduct.objects.create(
            profile=self.profile, remote_id="202", remote_parent_id="22", name="Soul Star 1000 ماسة",
            category=cat_star, cost_price=Decimal("2.00"), is_active=True, local_is_active=True
        )
        ProviderPrice.objects.create(product=pp_star, margin_value=Decimal("10.00"))

        # Map to catalog
        self.mapper_svc.map_all_to_catalog()

        prods = Product.objects.all()
        prod_names = [p.name for p in prods]

        # Must have exactly 2 distinct products: Soul Chill and Soul Star
        self.assertEqual(prods.count(), 2)
        self.assertTrue(any("سول تشيل" in name or "Soul Chill" in name for name in prod_names))
        self.assertTrue(any("سول ستار" in name or "Soul Star" in name for name in prod_names))

    def test_pubg_servers_mapped_to_pubg_not_standalone_server_product(self):
        """
        Verify that PUBG items with parent_id=10 are mapped under PUBG Mobile,
        and NO standalone 'سيرفر 1' product is created.
        """
        cat_games = ProviderCategory.objects.create(profile=self.profile, remote_id="1", name="شحن الألعاب")
        cat_pubg = ProviderCategory.objects.create(profile=self.profile, remote_id="10", name="PUBG Mobile", parent=cat_games)
        
        # Root PUBG product
        pp_pubg = ProviderProduct.objects.create(
            profile=self.profile, remote_id="10", remote_parent_id=None, name="ببجي موبايل (PUBG Mobile)",
            category=cat_pubg, cost_price=Decimal("0.00"), is_active=True, local_is_active=True
        )

        cat_srv1 = ProviderCategory.objects.create(profile=self.profile, remote_id="101", name="سيرفر 1", parent=cat_pubg)
        cat_srv2 = ProviderCategory.objects.create(profile=self.profile, remote_id="102", name="سيرفر 2", parent=cat_pubg)

        # Packages strictly having remote_parent_id="10"
        pp_60_s1 = ProviderProduct.objects.create(
            profile=self.profile, remote_id="301", remote_parent_id="10", name="60 شدة",
            category=cat_srv1, cost_price=Decimal("0.90"), is_active=True, local_is_active=True
        )
        ProviderPrice.objects.create(product=pp_60_s1, margin_value=Decimal("10.00"))

        pp_325_s1 = ProviderProduct.objects.create(
            profile=self.profile, remote_id="302", remote_parent_id="10", name="325 شدة",
            category=cat_srv1, cost_price=Decimal("4.50"), is_active=True, local_is_active=True
        )
        ProviderPrice.objects.create(product=pp_325_s1, margin_value=Decimal("10.00"))

        pp_60_s2 = ProviderProduct.objects.create(
            profile=self.profile, remote_id="303", remote_parent_id="10", name="60 شدة",
            category=cat_srv2, cost_price=Decimal("0.95"), is_active=True, local_is_active=True
        )
        ProviderPrice.objects.create(product=pp_60_s2, margin_value=Decimal("10.00"))

        # Map to catalog
        self.mapper_svc.map_all_to_catalog()

        # Check products: MUST NOT have a product named "سيرفر 1" or "سيرفر 2"
        self.assertFalse(Product.objects.filter(name__icontains="سيرفر 1").exists())
        self.assertFalse(Product.objects.filter(name__icontains="سيرفر 2").exists())

        # All 3 packages must be under PUBG Mobile
        pubg_prod = Product.objects.filter(name__icontains="ببجي").first()
        self.assertIsNotNone(pubg_prod)
        self.assertEqual(pubg_prod.variants.count(), 3)

        variants = list(pubg_prod.variants.all())
        self.assertTrue(all(v.provider_parent_id == 10 for v in variants))
        self.assertTrue(all(v.product_id == pubg_prod.id for v in variants))
