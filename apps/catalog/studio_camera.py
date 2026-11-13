import io
import os
import logging
from collections import deque
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw
from django.conf import settings

logger = logging.getLogger(__name__)

MASTER_BADGE_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_master_badge.png")
EMBLEM_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_emblem.png")


def _has_meaningful_alpha(img: Image.Image) -> bool:
    """Returns True if the RGBA image already has a real foreground/background alpha cutout."""
    if img.mode != "RGBA":
        return False
    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    if not extrema or extrema[0] >= 240:
        return False
    # Check corners to confirm background is transparent
    w, h = img.size
    corners = [
        alpha.getpixel((0, 0)),
        alpha.getpixel((w - 1, 0)),
        alpha.getpixel((0, h - 1)),
        alpha.getpixel((w - 1, h - 1)),
    ]
    return sum(1 for c in corners if c < 40) >= 2


def _remove_background_smart(img: Image.Image) -> Image.Image:
    """
    Pure-Pillow edge-aware border flood-fill background removal.
    Produces a smooth RGBA foreground cutout without requiring heavy ML runtimes on the server.
    """
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    # Work at <= 360px for fast BFS flood-fill, then upscale mask smoothly
    work_max = 360
    scale = min(work_max / orig_w, work_max / orig_h, 1.0)
    ww = max(32, int(orig_w * scale))
    wh = max(32, int(orig_h * scale))
    small = rgba.resize((ww, wh), Image.Resampling.BILINEAR)
    px = small.load()

    # Collect border seed colors (top, bottom, left, right)
    seeds = []
    border_samples = []
    for x in range(0, ww, max(1, ww // 24)):
        seeds.append((x, 0))
        seeds.append((x, wh - 1))
        border_samples.append(px[x, 0][:3])
        border_samples.append(px[x, wh - 1][:3])
    for y in range(0, wh, max(1, wh // 24)):
        seeds.append((0, y))
        seeds.append((ww - 1, y))
        border_samples.append(px[0, y][:3])
        border_samples.append(px[ww - 1, y][:3])

    avg_r = sum(c[0] for c in border_samples) / len(border_samples)
    avg_g = sum(c[1] for c in border_samples) / len(border_samples)
    avg_b = sum(c[2] for c in border_samples) / len(border_samples)

    # Estimate border color variance to adapt tolerance automatically
    var_sum = 0.0
    for c in border_samples:
        dr = c[0] - avg_r
        dg = c[1] - avg_g
        db = c[2] - avg_b
        var_sum += (dr * dr + dg * dg + db * db) ** 0.5
    avg_var = var_sum / len(border_samples)

    # Adaptive thresholds
    global_thresh = max(38.0, min(88.0, 46.0 + avg_var * 1.15))
    local_step_thresh = 28.0

    def color_dist(c1, c2):
        # Perceptual weighted Euclidean distance
        dr = c1[0] - c2[0]
        dg = c1[1] - c2[1]
        db = c1[2] - c2[2]
        return (0.30 * dr * dr + 0.59 * dg * dg + 0.11 * db * db) ** 0.5

    bg_mask = [[False] * ww for _ in range(wh)]
    queue = deque()

    for sx, sy in seeds:
        if not bg_mask[sy][sx]:
            c = px[sx, sy][:3]
            if color_dist(c, (avg_r, avg_g, avg_b)) <= global_thresh * 1.35:
                bg_mask[sy][sx] = True
                queue.append((sx, sy))

    bg_count = len(queue)
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while queue:
        cx, cy = queue.popleft()
        cur_c = px[cx, cy][:3]
        for dx, dy in neighbors:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < ww and 0 <= ny < wh and not bg_mask[ny][nx]:
                nc = px[nx, ny][:3]
                d_local = color_dist(cur_c, nc)
                d_global = color_dist(nc, (avg_r, avg_g, avg_b))
                if d_local <= local_step_thresh and d_global <= global_thresh:
                    bg_mask[ny][nx] = True
                    bg_count += 1
                    queue.append((nx, ny))

    fg_ratio = 1.0 - (bg_count / float(ww * wh))
    # Safety check: if segmentation ate almost everything or nothing, keep original
    if fg_ratio < 0.04 or fg_ratio > 0.96:
        return rgba

    # Build grayscale mask (255 = foreground, 0 = background)
    mask_small = Image.new("L", (ww, wh), 255)
    m_px = mask_small.load()
    for y in range(wh):
        row = bg_mask[y]
        for x in range(ww):
            if row[x]:
                m_px[x, y] = 0

    # Smooth edges and upscale back to full resolution
    mask_full = mask_small.resize((orig_w, orig_h), Image.Resampling.BILINEAR)
    mask_full = mask_full.filter(ImageFilter.GaussianBlur(radius=1.6))
    # Tighten alpha ramp slightly to remove background halo
    mask_full = mask_full.point(lambda a: 0 if a < 28 else (255 if a > 225 else int((a - 28) * 255 / 197)))

    out = rgba.copy()
    out.putalpha(mask_full)
    return out


def _create_studio_stage(target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """Creates a professional photography studio backdrop with subtle radial spotlight."""
    if bg_style == "studio_dark":
        base_col = (6, 10, 20, 255)
        center_col = (24, 38, 62, 255)
        horizon_col = (12, 18, 34, 255)
    else:
        base_col = (238, 242, 247, 255)
        center_col = (255, 255, 255, 255)
        horizon_col = (245, 247, 250, 255)

    stage = Image.new("RGBA", (target_size, target_size), base_col)

    # Soft radial spotlight behind the product
    glow = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    cx, cy = target_size // 2, int(target_size * 0.44)
    max_r = int(target_size * 0.62)
    steps = 18
    for i in range(steps, 0, -1):
        r = int(max_r * (i / steps))
        alpha = int(255 * (1.0 - (i / steps) ** 1.6))
        g_draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(center_col[0], center_col[1], center_col[2], min(255, alpha)),
        )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(8, target_size // 24)))
    stage = Image.alpha_composite(stage, glow)

    # Subtle studio floor cyclorama band at bottom 22%
    floor = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    f_draw = ImageDraw.Draw(floor)
    floor_y = int(target_size * 0.78)
    f_draw.rectangle([0, floor_y, target_size, target_size], fill=(horizon_col[0], horizon_col[1], horizon_col[2], 140))
    floor = floor.filter(ImageFilter.GaussianBlur(radius=max(6, target_size // 35)))
    stage = Image.alpha_composite(stage, floor)

    return stage


def _apply_raqamiyat_branding(canvas: Image.Image, target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """Applies the official Raqamiyat logo & verified studio hallmark cleanly."""
    # 1. Top-right subtle luxury emblem watermark (if available)
    if os.path.exists(EMBLEM_PATH):
        try:
            emblem = Image.open(EMBLEM_PATH).convert("RGBA")
            emb_size = max(44, int(target_size * 0.10))
            emblem_resized = emblem.resize((emb_size, emb_size), Image.Resampling.LANCZOS)
            pad = int(target_size * 0.035)
            canvas.paste(emblem_resized, (target_size - emb_size - pad, pad), emblem_resized)
        except Exception as ee:
            logger.warning("Could not apply emblem: %s", ee)

    # 2. Bottom centered official Raqamiyat master badge
    if os.path.exists(MASTER_BADGE_PATH):
        try:
            badge = Image.open(MASTER_BADGE_PATH).convert("RGBA")
            target_bw = int(target_size * 0.56)
            target_bh = max(16, int(badge.height * (target_bw / badge.width)))
            badge_resized = badge.resize((target_bw, target_bh), Image.Resampling.LANCZOS)

            bx = (target_size - target_bw) // 2
            by = target_size - target_bh - int(target_size * 0.032)

            b_shadow = Image.new("RGBA", (target_bw + 24, target_bh + 24), (0, 0, 0, 0))
            bs_draw = ImageDraw.Draw(b_shadow)
            shadow_alpha = 110 if bg_style == "studio_white" else 170
            bs_draw.rounded_rectangle(
                [12, 12, 12 + target_bw, 12 + target_bh],
                radius=max(6, target_bh // 2),
                fill=(0, 0, 0, shadow_alpha),
            )
            b_shadow = b_shadow.filter(ImageFilter.GaussianBlur(6))

            canvas.paste(b_shadow, (bx - 12, by - 10), b_shadow)
            canvas.paste(badge_resized, (bx, by), badge_resized)
        except Exception as be:
            logger.warning("Could not apply hallmark badge: %s", be)

    return canvas


def process_camera_product_snapshot(
    image_file,
    isolate_white=True,
    add_hallmark=True,
    target_size=800,
    store_name=None,
    bg_style="studio_white",
):
    """
    Transforms a raw mobile camera product photo into a luxury e-commerce studio shot:
    1. EXIF Auto-Orientation: Fixes mobile camera rotation.
    2. Smart Background Removal: Preserves on-device ML Kit alpha cutout if present,
       or performs edge-aware flood-fill background removal.
    3. Studio Stage & Contact Shadow: Composites onto a lit studio cyclorama with
       realistic contact shadow and color/sharpness polish.
    4. Raqamiyat Branding: Adds official Raqamiyat emblem & verified hallmark.
    """
    try:
        if hasattr(image_file, "read"):
            raw_bytes = image_file.read()
            img = Image.open(io.BytesIO(raw_bytes))
        elif isinstance(image_file, bytes):
            img = Image.open(io.BytesIO(image_file))
        else:
            img = Image.open(image_file)

        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        img = img.convert("RGBA")

        # Downscale massive 48MP-200MP sensors for fast processing
        max_dim = 1600
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        if isolate_white:
            # Remove background unless caller (e.g. Android ML Kit) already supplied a clean alpha mask
            if not _has_meaningful_alpha(img):
                img = _remove_background_smart(img)

            # Auto-crop to foreground bounding box with small safety margin
            alpha = img.getchannel("A")
            bbox = alpha.point(lambda a: 255 if a > 24 else 0).getbbox()
            if bbox:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                if bw > 20 and bh > 20:
                    img = img.crop(bbox)

            w, h = img.size
            canvas = _create_studio_stage(target_size, bg_style=bg_style)

            # Fit product cleanly inside 70% of frame, leaving room at bottom for badge
            max_prod_w = int(target_size * 0.74)
            max_prod_h = int(target_size * 0.68)
            scale = min(max_prod_w / w, max_prod_h / h)
            nw = max(16, int(w * scale))
            nh = max(16, int(h * scale))
            resized_prod = img.resize((nw, nh), Image.Resampling.LANCZOS)

            # Studio polish (preserve alpha)
            r, g, b, a = resized_prod.split()
            rgb_prod = Image.merge("RGB", (r, g, b))
            rgb_prod = ImageEnhance.Contrast(rgb_prod).enhance(1.08)
            rgb_prod = ImageEnhance.Sharpness(rgb_prod).enhance(1.22)
            rgb_prod = ImageEnhance.Color(rgb_prod).enhance(1.06)
            r2, g2, b2 = rgb_prod.split()
            resized_prod = Image.merge("RGBA", (r2, g2, b2, a))

            px = (target_size - nw) // 2
            py = int(target_size * 0.44) - (nh // 2)
            py = max(int(target_size * 0.07), py)

            # Multi-layer realistic contact shadow under product
            shadow = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            shadow_w = max(28, int(nw * 0.72))
            shadow_h = max(12, int(target_size * 0.045))
            sx1 = (target_size - shadow_w) // 2
            sy1 = min(target_size - shadow_h - 40, py + nh - (shadow_h // 3))
            s_draw.ellipse([sx1, sy1, sx1 + shadow_w, sy1 + shadow_h], fill=(15, 23, 42, 42))
            core_w = int(shadow_w * 0.6)
            core_h = max(6, shadow_h // 2)
            cx1 = (target_size - core_w) // 2
            cy1 = sy1 + (shadow_h - core_h) // 2
            s_draw.ellipse([cx1, cy1, cx1 + core_w, cy1 + core_h], fill=(15, 23, 42, 65))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(6, shadow_h // 2)))
            canvas = Image.alpha_composite(canvas, shadow)

            # Composite isolated product
            canvas.paste(resized_prod, (px, py), resized_prod)
        else:
            w, h = img.size
            min_side = min(w, h)
            crop_x = (w - min_side) // 2
            crop_y = (h - min_side) // 2
            square_img = img.crop((crop_x, crop_y, crop_x + min_side, crop_y + min_side))
            canvas = square_img.resize((target_size, target_size), Image.Resampling.LANCZOS)
            canvas = ImageEnhance.Contrast(canvas).enhance(1.08)
            canvas = ImageEnhance.Sharpness(canvas).enhance(1.2)

        if add_hallmark:
            canvas = _apply_raqamiyat_branding(canvas, target_size, bg_style=bg_style)

        final_img = canvas.convert("RGB")
        buf = io.BytesIO()
        final_img.save(buf, format="JPEG", quality=93, optimize=True)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.error("Error in process_camera_product_snapshot: %s", e)
        raise
