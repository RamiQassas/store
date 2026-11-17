import os
import sys
import shutil
import threading
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

        try:
            argv_str = " ".join(sys.argv).lower()
            is_web_server = (
                "runserver" in argv_str
                or "gunicorn" in argv_str
                or "uvicorn" in argv_str
                or "daphne" in argv_str
                or "uwsgi" in argv_str
            )
            marker = os.path.join(str(settings.MEDIA_ROOT), ".studio_white_450_v1_done")
            if is_web_server and not os.path.exists(marker):
                def _bg_upgrade():
                    try:
                        import time
                        time.sleep(8)
                        from apps.catalog.management.commands.enhance_all_catalog_images import run_batch_studio_white_upgrade
                        run_batch_studio_white_upgrade(force=False)
                    except Exception:
                        pass
                threading.Thread(target=_bg_upgrade, daemon=True).start()
        except Exception:
            pass
