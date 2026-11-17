import json
import logging
import os
import shutil
from collections import deque

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageFilter

from apps.catalog.models import Category, Product
from apps.catalog.studio_camera import process_camera_product_snapshot

logger = logging.getLogger(__name__)


def _extract_dark_card_to_white_studio(path: str) -> bytes:
    """
    Cleanly removes the broken bottom bar and dark radial background from legacy 800x800
    dark product cards using edge-stopped border flood-fill, then renders onto studio_white.
    """
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    top = im.crop((0, int(h * 0.03), w, int(h * 0.80)))
    tw, th = top.size
    sw, sh = 400, max(32, int(400 * th / tw))
    small = top.resize((sw, sh), Image.Resampling.BILINEAR)
    rgb = np.asarray(small.convert("RGB"), dtype=np.float32)
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    edges = np.asarray(small.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)

    bg = np.zeros((sh, sw), dtype=bool)
    q = deque()
    for x in range(sw):
        bg[0, x] = True
        q.append((x, 0))
        bg[sh - 1, x] = True
        q.append((x, sh - 1))
    for y in range(sh):
        if not bg[y, 0]:
            bg[y, 0] = True
            q.append((0, y))
        if not bg[y, sw - 1]:
            bg[y, sw - 1] = True
            q.append((sw - 1, y))

    while q:
        cx, cy = q.popleft()
        c_rgb = rgb[cy, cx]
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < sw and 0 <= ny < sh and not bg[ny, nx]:
                if 2 <= nx < sw - 2 and 2 <= ny < sh - 2 and edges[ny, nx] > 18:
                    continue
                n_rgb = rgb[ny, nx]
                if float(np.max(np.abs(n_rgb - c_rgb))) <= 8.0 and gray[ny, nx] < 65:
                    bg[ny, nx] = True
                    q.append((nx, ny))

    mask_small = Image.fromarray((~bg).astype(np.uint8) * 255, mode="L")
    mask_full = mask_small.resize((tw, th), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(0.8))
    top.putalpha(mask_full)
    return process_camera_product_snapshot(
        top,
        isolate_white=True,
        add_hallmark=True,
        bg_style="studio_white",
        filter_mode="auto_hdr",
        auto_straighten=False,
    )


def run_batch_studio_white_upgrade(force: bool = False) -> dict:
    media_root = str(settings.MEDIA_ROOT)
    marker = os.path.join(media_root, ".studio_white_450_v1_done")
    if os.path.exists(marker) and not force:
        return {"skipped": True, "reason": "already_done"}

    # 1. Safety Backup of all media/products, media/categories & DB ordering
    backup_dir = os.path.join(media_root, "backups", "pre_studio_white_v1")
    os.makedirs(backup_dir, exist_ok=True)
    for sub in ("products", "categories"):
        src_sub = os.path.join(media_root, sub)
        dst_sub = os.path.join(backup_dir, sub)
        if os.path.exists(src_sub) and not os.path.exists(dst_sub):
            shutil.copytree(src_sub, dst_sub, dirs_exist_ok=True)

    manifest_path = os.path.join(backup_dir, "catalog_order_backup.json")
    if not os.path.exists(manifest_path):
        cats = [
            {
                "id": str(c.id),
                "name": c.name,
                "sort_order": getattr(c, "sort_order", 0),
                "image": c.image.name if c.image else "",
            }
            for c in Category.all_objects.all()
        ]
        prods = [
            {
                "id": str(p.id),
                "name": p.name,
                "category_id": str(p.category_id) if p.category_id else "",
                "sort_order": getattr(p, "sort_order", 0),
                "image": p.image.name if p.image else "",
            }
            for p in Product.all_objects.all()
        ]
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump({"categories": cats, "products": prods}, mf, ensure_ascii=False, indent=2)

    # 2. Collect all product image paths (DB + any files inside media/products/)
    target_paths = set()
    for p in Product.all_objects.all():
        if p.image:
            try:
                if os.path.exists(p.image.path):
                    target_paths.add(os.path.abspath(p.image.path))
            except Exception:
                pass

    products_dir = os.path.join(media_root, "products")
    if os.path.exists(products_dir):
        for dp, _, fns in os.walk(products_dir):
            for fn in fns:
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    target_paths.add(os.path.abspath(os.path.join(dp, fn)))

    upgraded_dark = 0
    upgraded_photo = 0
    failed = 0

    for path in sorted(target_paths):
        if os.path.basename(path) == "raqamiyat_official_brand_product.jpg":
            continue
        try:
            with Image.open(path) as im:
                rgb = np.asarray(im.convert("RGB").resize((64, 64)), dtype=np.float32)
                corners = np.concatenate([rgb[0, :8], rgb[0, -8:], rgb[-1, :8], rgb[-1, -8:]], axis=0)
                mean_c = float(corners.mean())
                is_square_800 = im.size == (800, 800)

            if mean_c < 40.0 and is_square_800:
                out_bytes = _extract_dark_card_to_white_studio(path)
                upgraded_dark += 1
            else:
                out_bytes = process_camera_product_snapshot(
                    path,
                    isolate_white=True,
                    add_hallmark=True,
                    bg_style="studio_white",
                    filter_mode="auto_hdr",
                    auto_straighten=True,
                )
                upgraded_photo += 1

            with open(path, "wb") as out_f:
                out_f.write(out_bytes)
        except Exception as exc:
            failed += 1
            logger.warning("Studio white upgrade skipped %s: %s", path, exc)

    try:
        from django.core.cache import cache
        cache.delete("api_offline_catalog_data")
    except Exception:
        pass

    with open(marker, "w", encoding="utf-8") as mk:
        mk.write(f"dark={upgraded_dark},photo={upgraded_photo},failed={failed}\n")

    return {"dark": upgraded_dark, "photo": upgraded_photo, "failed": failed}


class Command(BaseCommand):
    help = "Backs up and AI-enhances all existing product images onto pure studio_white backgrounds."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Re-run even if already marked done.")

    def handle(self, *args, **options):
        res = run_batch_studio_white_upgrade(force=bool(options.get("force")))
        self.stdout.write(self.style.SUCCESS(f"Studio White Upgrade Result: {res}"))
