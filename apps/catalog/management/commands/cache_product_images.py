import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.catalog.models import Product
from apps.catalog.smart_branding import apply_branding_to_product
from apps.catalog.image_caching import match_brand_static_asset

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cache and store high-quality local images on the server for all products without an image.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-branding and caching even if product already has an image.',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        products = Product.objects.all()
        total = products.count()
        self.stdout.write(f'Scanning {total} products for image caching...')

        updated_count = 0
        skipped_count = 0

        for p in products:
            has_valid_image = False
            if p.image:
                try:
                    if p.image.storage.exists(p.image.name):
                        has_valid_image = True
                except Exception:
                    has_valid_image = False

            if has_valid_image and not force:
                skipped_count += 1
                continue

            try:
                success = apply_branding_to_product(p, force=force)
                if success:
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f'Cached image for: {p.name}'))
                else:
                    skipped_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Could not cache image for {p.name}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Done! Successfully cached images for {updated_count} products ({skipped_count} skipped).'))
