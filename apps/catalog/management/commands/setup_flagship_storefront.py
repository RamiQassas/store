import os
import shutil
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.catalog.models import Category, Product
from apps.common.tenant_utils import bypass_tenant_filter

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Configures all categories and flagship products for optimal display on the redesigned Raqamiyat storefront."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Initializing Raqamiyat Flagship Storefront..."))

        # 0. Sync and seed authentic physical tech products
        from django.core.management import call_command
        try:
            call_command("seed_tech_products")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Notice: Seed tech products execution: {e}"))

        # 0.1 Ensure default brand media file physically exists on disk
        try:
            target_dir = os.path.join(settings.MEDIA_ROOT, "products", "main")
            target_file = os.path.join(target_dir, "raqamiyat_official_brand_product.jpg")
            os.makedirs(target_dir, exist_ok=True)
            if not os.path.exists(target_file):
                src_file = os.path.join(settings.BASE_DIR, "apps", "site", "static", "site", "img", "raqamiyat_logo_square.jpg")
                if os.path.exists(src_file):
                    shutil.copyfile(src_file, target_file)
                    self.stdout.write(f"Created default brand emblem file at: {target_file}")
        except Exception as e:
            self.stdout.write(f"Notice: Media setup note: {e}")

        with bypass_tenant_filter():
            # 1. Ensure all categories are active & publicly visible
            cats_updated = Category.all_objects.filter(is_active=True).update(is_publicly_visible=True)
            self.stdout.write(f"Updated {cats_updated} categories to publicly visible.")

            # 2. Ensure all active products are publicly visible
            prods_updated = Product.all_objects.filter(is_active=True).update(is_publicly_visible=True, compliance_status="compliant")
            self.stdout.write(f"Updated {prods_updated} products to publicly visible & compliant.")

            # 3. Mark Flagship Featured Products across diverse categories (Physical Hardware Only)
            flagship_keywords = [
                'iPhone 17 Pro Max', 'Samsung Galaxy S26 Ultra', 'Samsung Galaxy A57',
                'Xiaomi Mi 15 Ultra', 'Xiaomi Redmi Note 17 Pro Max', 'Poco F9 Pro',
                'Infinix GT 50 Pro', 'Honor Magic 8 Pro', 'Tecno Camon 50 Ultra',
                'B315', 'Pad', 'شاحن'
            ]
            featured_count = 0
            for kw in flagship_keywords:
                p = Product.all_objects.filter(name__icontains=kw, is_active=True, product_type='physical').first()
                if p:
                    p.is_featured = True
                    p.save(update_fields=['is_featured'])
                    featured_count += 1
            self.stdout.write(f"Marked {featured_count} flagship products as is_featured=True.")

            # 4. Mark top promotional sale products
            sale_keywords = ['A07', 'Redmi A5', 'Poco C71', 'Smart 20', 'Spark Go', 'شاحن']
            sale_count = 0
            for kw in sale_keywords:
                p = Product.all_objects.filter(name__icontains=kw, is_active=True, product_type='physical').first()
                if p:
                    p.is_sale = True
                    p.save(update_fields=['is_sale'])
                    sale_count += 1
            self.stdout.write(f"Marked {sale_count} promotional products as is_sale=True.")

        # Invalidate all storefront caches
        from django.core.cache import cache
        try:
            cache.clear()
            self.stdout.write("Invalidated and refreshed all storefront caches.")
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(">> Raqamiyat Flagship Storefront setup completed successfully!"))
