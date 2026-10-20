import os
import shutil
from django.apps import AppConfig
from django.conf import settings


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"

    def ready(self):
        try:
            target_dir = os.path.join(settings.MEDIA_ROOT, "products", "main")
            target_file = os.path.join(target_dir, "raqamiyat_official_brand_product.jpg")
            if not os.path.exists(target_file):
                os.makedirs(target_dir, exist_ok=True)
                src_file = os.path.join(settings.BASE_DIR, "apps", "site", "static", "site", "img", "raqamiyat_logo_square.jpg")
                if os.path.exists(src_file):
                    shutil.copyfile(src_file, target_file)
        except Exception:
            pass
