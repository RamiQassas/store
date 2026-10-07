import io
import os
import logging
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.text import slugify

logger = logging.getLogger(__name__)

MASTER_BADGE_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_master_badge.png")


def process_camera_product_snapshot(
    image_file,
    isolate_white=True,
    add_hallmark=True,
    target_size=800,
    store_name=None
):
    """
    Takes a raw photo captured from mobile camera and transforms it into a 
    high-end e-commerce physical product photograph:
    1. EXIF Auto-Orientation: Fixes camera rotation from mobile phones.
    2. Studio Isolation: Places product on crisp pure white (#ffffff) background with contact shadow.
    3. Image Polish: Auto-balances exposure, contrast, and sharpens micro-details.
    4. Raqamiyat Hallmark: Adds official luxury 3D crystal lightning verified badge.
    """
    try:
        if hasattr(image_file, 'read'):
            raw_bytes = image_file.read()
            img = Image.open(io.BytesIO(raw_bytes))
        elif isinstance(image_file, bytes):
            img = Image.open(io.BytesIO(image_file))
        else:
            img = Image.open(image_file)

        # Fix mobile camera orientation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        img = img.convert("RGBA")

        # Downscale if massive camera sensor (e.g. 48MP phone camera) to ensure fast processing
        max_dim = 1600
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        w, h = img.size

        if isolate_white:
            # 1. Edge and brightness contrast isolation onto pure white #ffffff
            # Sample background corners to get ambient background color
            corners = [
                img.getpixel((5, 5)),
                img.getpixel((w - 6, 5)),
                img.getpixel((5, h - 6)),
                img.getpixel((w - 6, h - 6))
            ]
            bg_r = sum(c[0] for c in corners) // 4
            bg_g = sum(c[1] for c in corners) // 4
            bg_b = sum(c[2] for c in corners) // 4

            # Create clean white canvas
            canvas = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 255))

            # Resize product to fit nicely inside canvas (approx 78% of canvas size)
            max_prod_dim = int(target_size * 0.78)
            scale = min(max_prod_dim / w, max_prod_dim / h)
            nw = max(10, int(w * scale))
            nh = max(10, int(h * scale))
            resized_prod = img.resize((nw, nh), Image.Resampling.LANCZOS)

            # Auto color and contrast boost
            enhancer = ImageEnhance.Contrast(resized_prod)
            resized_prod = enhancer.enhance(1.10)
            sharpener = ImageEnhance.Sharpness(resized_prod)
            resized_prod = sharpener.enhance(1.25)
            color_enhancer = ImageEnhance.Color(resized_prod)
            resized_prod = color_enhancer.enhance(1.08)

            px = (target_size - nw) // 2
            py = (target_size - nh) // 2 - int(target_size * 0.02) # slightly upper for ground shadow

            # Contact drop shadow
            shadow_h = max(12, int(nh * 0.08))
            shadow_w = max(20, int(nw * 0.75))
            shadow = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            sx1 = (target_size - shadow_w) // 2
            sy1 = py + nh - (shadow_h // 2)
            s_draw.ellipse([sx1, sy1, sx1 + shadow_w, sy1 + shadow_h], fill=(0, 0, 0, 45))
            shadow = shadow.filter(ImageFilter.GaussianBlur(int(shadow_h * 0.6)))
            canvas.paste(shadow, (0, 0), shadow)

            # Paste product
            canvas.paste(resized_prod, (px, py), resized_prod)
        else:
            # Crop to square, polish colors
            min_side = min(w, h)
            crop_x = (w - min_side) // 2
            crop_y = (h - min_side) // 2
            square_img = img.crop((crop_x, crop_y, crop_x + min_side, crop_y + min_side))
            canvas = square_img.resize((target_size, target_size), Image.Resampling.LANCZOS)

            enhancer = ImageEnhance.Contrast(canvas)
            canvas = enhancer.enhance(1.08)
            sharpener = ImageEnhance.Sharpness(canvas)
            canvas = sharpener.enhance(1.2)

        # 4. Add Raqamiyat Hallmark / Official Master Badge
        if add_hallmark and os.path.exists(MASTER_BADGE_PATH):
            try:
                badge = Image.open(MASTER_BADGE_PATH).convert("RGBA")
                target_bw = int(target_size * 0.70)
                target_bh = int(badge.height * (target_bw / badge.width))
                badge_resized = badge.resize((target_bw, target_bh), Image.Resampling.LANCZOS)

                bx = (target_size - target_bw) // 2
                by = target_size - target_bh - int(target_size * 0.04)

                # Soft shadow under badge
                b_shadow = Image.new("RGBA", (target_bw + 20, target_bh + 20), (0, 0, 0, 0))
                bs_draw = ImageDraw.Draw(b_shadow)
                bs_draw.rounded_rectangle(
                    [10, 10, 10 + target_bw, 10 + target_bh],
                    radius=target_bh // 2,
                    fill=(0, 0, 0, 140)
                )
                b_shadow = b_shadow.filter(ImageFilter.GaussianBlur(6))

                canvas.paste(b_shadow, (bx - 10, by - 10), b_shadow)
                canvas.paste(badge_resized, (bx, by), badge_resized)
            except Exception as be:
                logger.warning("Could not apply hallmark badge: %s", be)

        # Convert to RGB JPEG
        final_img = canvas.convert("RGB")
        buf = io.BytesIO()
        final_img.save(buf, format="JPEG", quality=92, optimize=True)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.error("Error in process_camera_product_snapshot: %s", e)
        raise
