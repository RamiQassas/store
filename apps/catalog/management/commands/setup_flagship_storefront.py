import logging
from django.core.management.base import BaseCommand
from apps.catalog.models import Category, Product
from apps.common.tenant_utils import bypass_tenant_filter

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Configures all categories and flagship products for optimal display on the redesigned Raqamiyat storefront."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Initializing Raqamiyat Flagship Storefront..."))

        with bypass_tenant_filter():
            # 1. Ensure all categories are active & publicly visible
            cats_updated = Category.all_objects.filter(is_active=True).update(is_publicly_visible=True)
            self.stdout.write(f"Updated {cats_updated} categories to publicly visible.")

            # 2. Ensure all active products are publicly visible
            prods_updated = Product.all_objects.filter(is_active=True).update(is_publicly_visible=True, compliance_status="compliant")
            self.stdout.write(f"Updated {prods_updated} products to publicly visible & compliant.")

            # 3. Mark Flagship Featured Products across diverse categories
            flagship_keywords = [
                'PUBG', 'PlayStation', 'Steam', 'iTunes', 'Router', 'Cabinet',
                'ChatGPT', 'Windows', 'Netflix', 'MTN', 'Free Fire', 'Roblox'
            ]
            featured_count = 0
            for kw in flagship_keywords:
                p = Product.all_objects.filter(name__icontains=kw, is_active=True).first()
                if p:
                    p.is_featured = True
                    p.save(update_fields=['is_featured'])
                    featured_count += 1
            self.stdout.write(f"Marked {featured_count} flagship products as is_featured=True.")

            # 4. Mark top promotional sale products
            sale_keywords = ['PUBG', 'Steam', 'Free Fire', 'Netflix']
            sale_count = 0
            for kw in sale_keywords:
                p = Product.all_objects.filter(name__icontains=kw, is_active=True).first()
                if p:
                    p.is_sale = True
                    p.save(update_fields=['is_sale'])
                    sale_count += 1
            self.stdout.write(f"Marked {sale_count} promotional products as is_sale=True.")

        self.stdout.write(self.style.SUCCESS(">> Raqamiyat Flagship Storefront setup completed successfully!"))
