import io
import os
import sys
import logging
import subprocess
from collections import deque
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw
from django.conf import settings

logger = logging.getLogger(__name__)

MASTER_BADGE_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_master_badge.png")
EMBLEM_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_emblem.png")
U2NETP_ONNX_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "u2netp.onnx")
U2NETP_FALLBACK_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"

_ORT_SESSION = None
_ORT_INIT_ATTEMPTED = False


def _ensure_ai_runtime():
    """
    Lazily loads the ONNX Runtime session for U2Netp Salient Object Detection.
    If numpy/onnxruntime are not yet installed in the container, attempts a fast
    one-time pip install so the live server upgrades without requiring Docker rebuild.
    """
    global _ORT_SESSION, _ORT_INIT_ATTEMPTED
    if _ORT_SESSION is not None:
        return _ORT_SESSION
    if _ORT_INIT_ATTEMPTED:
        return None
    _ORT_INIT_ATTEMPTED = True

    try:
        import numpy as np  # noqa: F401
        import onnxruntime as ort
    except ImportError:
        try:
            py_bin = sys.executable or "python"
            subprocess.run(
                [py_bin, "-m", "pip", "install", "--no-cache-dir", "-q", "numpy", "onnxruntime"],
                timeout=90,
                check=False,
            )
            import numpy as np  # noqa: F401
            import onnxruntime as ort
        except Exception as e:
            logger.warning("Could not load/install onnxruntime for studio camera: %s", e)
            return None

    try:
        model_path = U2NETP_ONNX_PATH
        if not os.path.exists(model_path) or os.path.getsize(model_path) < 1000000:
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            import requests
            r = requests.get(U2NETP_FALLBACK_URL, timeout=25)
            if r.status_code == 200 and len(r.content) > 1000000:
                with open(model_path, "wb") as f:
                    f.write(r.content)

        if os.path.exists(model_path):
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 2
            sess_opts.inter_op_num_threads = 1
            _ORT_SESSION = ort.InferenceSession(
                model_path,
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )
            return _ORT_SESSION
    except Exception as e:
        logger.warning("Failed initializing U2Netp ONNX session: %s", e)
    return None


def _has_meaningful_alpha(img: Image.Image) -> bool:
    """Returns True if the RGBA image already has a foreground/background alpha cutout."""
    if img.mode != "RGBA":
        return False
    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    if not extrema or extrema[0] >= 240:
        return False
    w, h = img.size
    corners = [
        alpha.getpixel((0, 0)),
        alpha.getpixel((w - 1, 0)),
        alpha.getpixel((0, h - 1)),
        alpha.getpixel((w - 1, h - 1)),
    ]
    return sum(1 for c in corners if c < 40) >= 2


def _run_u2net_pass(sess, rgb_img: Image.Image):
    """Runs a single 320x320 U2Netp forward pass and returns a [0..1] float32 salience map."""
    import numpy as np

    inp = rgb_img.resize((320, 320), Image.Resampling.BILINEAR)
    arr = np.asarray(inp, dtype=np.float32)
    max_val = float(arr.max())
    if max_val > 0:
        arr = arr / max_val
    arr[:, :, 0] = (arr[:, :, 0] - 0.485) / 0.229
    arr[:, :, 1] = (arr[:, :, 1] - 0.456) / 0.224
    arr[:, :, 2] = (arr[:, :, 2] - 0.406) / 0.225
    tensor = np.transpose(arr, (2, 0, 1))[np.newaxis, :, :, :].astype(np.float32)
    input_name = sess.get_inputs()[0].name
    pred = sess.run(None, {input_name: tensor})[0][0, 0]
    p_min, p_max = float(pred.min()), float(pred.max())
    if p_max - p_min > 1e-6:
        pred = (pred - p_min) / (p_max - p_min)
    else:
        pred = np.zeros_like(pred)
    return pred


def _filter_central_components_and_fill_holes(mask_320):
    """
    Keeps only the primary foreground subject connected to the central camera guide frame,
    eliminating disconnected background room clutter (cords, plants, side boxes, wall marks),
    and fills interior holes inside the subject.
    """
    import numpy as np

    h, w = mask_320.shape
    binary = mask_320 > 0.36
    if not binary.any():
        return mask_320

    visited = np.zeros((h, w), dtype=bool)
    labels = np.zeros((h, w), dtype=np.int32)
    comp_scores = {}
    cur_label = 0

    # Central guide zone where the user positions the product
    cx_ideal, cy_ideal = w * 0.50, h * 0.48
    core_x1, core_x2 = int(w * 0.28), int(w * 0.72)
    core_y1, core_y2 = int(h * 0.18), int(h * 0.82)

    for y in range(h):
        for x in range(w):
            if binary[y, x] and not visited[y, x]:
                cur_label += 1
                q = deque([(x, y)])
                visited[y, x] = True
                labels[y, x] = cur_label
                area = 0
                sum_x = 0.0
                sum_y = 0.0
                core_hits = 0
                prob_sum = 0.0
                touches_outer_edge = False

                while q:
                    cx, cy = q.popleft()
                    area += 1
                    sum_x += cx
                    sum_y += cy
                    prob_sum += float(mask_320[cy, cx])
                    if core_x1 <= cx <= core_x2 and core_y1 <= cy <= core_y2:
                        core_hits += 1
                    if cx <= 2 or cx >= w - 3 or cy <= 2 or cy >= h - 3:
                        touches_outer_edge = True

                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and binary[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            labels[ny, nx] = cur_label
                            q.append((nx, ny))

                if area < 12:
                    continue

                mean_x = sum_x / area
                mean_y = sum_y / area
                dist_norm = (((mean_x - cx_ideal) / w) ** 2 + ((mean_y - cy_ideal) / h) ** 2) ** 0.5
                core_fraction = core_hits / float(area)
                mean_prob = prob_sum / float(area)

                # Reject peripheral room clutter that barely overlaps the center framing core
                if core_fraction < 0.15 and dist_norm > 0.24:
                    continue
                if touches_outer_edge and core_fraction < 0.35:
                    continue

                center_weight = max(0.05, 1.0 - dist_norm * 1.65)
                score = (area ** 0.85) * center_weight * (0.4 + 0.6 * core_fraction) * mean_prob
                comp_scores[cur_label] = (score, mean_x, mean_y, area, core_fraction)

    if not comp_scores:
        return mask_320

    best_label = max(comp_scores.keys(), key=lambda k: comp_scores[k][0])
    best_score, best_x, best_y, best_area, _ = comp_scores[best_label]

    keep_mask = labels == best_label
    # Also keep secondary components only if they are vertically aligned parts of the same product
    # (e.g., bottle cap/logo separated from bottom rim on a white product)
    for lbl, (sc, mx, my, area, cf) in comp_scores.items():
        if lbl == best_label:
            continue
        horiz_dist = abs(mx - best_x) / float(w)
        if cf > 0.55 and horiz_dist < 0.14 and sc >= best_score * 0.08:
            keep_mask |= (labels == lbl)

    cleaned = np.where(keep_mask, mask_320, 0.0).astype(np.float32)

    # Fill enclosed interior holes (flood fill background from borders of 320x320 grid)
    fg_solid = cleaned > 0.30
    bg_reach = np.zeros((h, w), dtype=bool)
    bg_q = deque()
    for x in range(w):
        if not fg_solid[0, x]:
            bg_reach[0, x] = True
            bg_q.append((x, 0))
        if not fg_solid[h - 1, x]:
            bg_reach[h - 1, x] = True
            bg_q.append((x, h - 1))
    for y in range(h):
        if not fg_solid[y, 0] and not bg_reach[y, 0]:
            bg_reach[y, 0] = True
            bg_q.append((0, y))
        if not fg_solid[y, w - 1] and not bg_reach[y, w - 1]:
            bg_reach[y, w - 1] = True
            bg_q.append((w - 1, y))

    while bg_q:
        cx, cy = bg_q.popleft()
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg_reach[ny, nx] and not fg_solid[ny, nx]:
                bg_reach[ny, nx] = True
                bg_q.append((nx, ny))

    interior_holes = ~bg_reach & ~fg_solid
    cleaned = np.where(interior_holes, 1.0, cleaned)
    return cleaned


def _reconstruct_white_product_if_hollow(rgba_img: Image.Image, mask_arr):
    """
    Handles the classic mobile studio failure mode where a white/bright container or bottle
    (such as a white POND'S bottle or white gadget box) is photographed against a bright wall
    with dark objects in the room:
    - Detects when the central vertical product spine is predominantly white/bright (>215)
      while the segmentation mask only captured interior markings (top brand logo + bottom rim)
      or lateral dark background objects.
    - Strips away peripheral & lateral background clutter.
    - Reconstructs a solid, 3D studio-shaded pearl-white container silhouette while keeping
      100% of the product's real brand text, logo, and surface details sharp.
    """
    import numpy as np

    h, w = mask_arr.shape
    # Composite over white first so if rgba_img came from a premultiplied PNG cutout where
    # white bottle pixels were erased to (0,0,0,0), those pixels are evaluated as bright white.
    white_bg = Image.new("RGBA", (w, h), (250, 251, 253, 255))
    comp_rgb_img = Image.alpha_composite(white_bg, rgba_img.convert("RGBA")).convert("RGB")
    rgb = np.asarray(comp_rgb_img, dtype=np.float32)
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    # Also detect dark/colored markings directly from pixel luminance in case mask missed them
    dark_markings = gray < 205
    fg_bin = (mask_arr > 80) | dark_markings

    # First, always strip isolated peripheral corner clutter (like top-right hanging cords/plants)
    # that lie outside the central product framing zone
    corner_clutter = np.zeros((h, w), dtype=bool)
    corner_clutter[:int(h * 0.34), int(w * 0.68):] = True
    corner_clutter[:int(h * 0.34), :int(w * 0.32)] = True
    mask_arr = np.where(corner_clutter, 0, mask_arr).astype(np.uint8)
    fg_bin = fg_bin & (~corner_clutter)

    cx1, cx2 = int(w * 0.38), int(w * 0.62)
    cy1, cy2 = int(h * 0.20), int(h * 0.68)
    spine_gray = gray[cy1:cy2, cx1:cx2]
    spine_mask = (mask_arr[cy1:cy2, cx1:cx2] > 110)
    bright_ratio = float((spine_gray > 216).mean())
    mask_fill_ratio = float(spine_mask.mean())

    # Trigger reconstruction if the central product spine is mostly bright white (>68%)
    # and the alpha mask is hollow/sparse (<50% filled)
    if bright_ratio > 0.68 and mask_fill_ratio < 0.50:
        lx1, lx2 = int(w * 0.40), int(w * 0.62)
        ly1, ly2 = int(h * 0.18), int(h * 0.44)
        logo_ys, logo_xs = np.where(fg_bin[ly1:ly2, lx1:lx2])

        bx1, bx2 = int(w * 0.36), int(w * 0.64)
        by1, by2 = int(h * 0.44), int(h * 0.74)
        bot_ys, bot_xs = np.where(fg_bin[by1:by2, bx1:bx2])

        if len(logo_ys) > 8 and len(bot_ys) > 8:
            y_logo_top = int(np.percentile(logo_ys + ly1, 5))
            y_base_bot = int(np.percentile(bot_ys + by1, 96))

            if y_base_bot - y_logo_top >= int(h * 0.14):
                rim_left = int(np.percentile(bot_xs + bx1, 3))
                rim_right = int(np.percentile(bot_xs + bx1, 97))
                logo_cx = int(np.median(logo_xs + lx1))
                rim_cx = (rim_left + rim_right) // 2
                bottle_cx = int(0.55 * rim_cx + 0.45 * logo_cx)

                # Detect inner occlusion edges if a dark background object sits behind the white product
                mid_y1, mid_y2 = int(h * 0.35), int(h * 0.58)
                inner_left = rim_left
                for x in range(bottle_cx - 12, int(w * 0.24), -1):
                    if fg_bin[mid_y1:mid_y2, x].mean() > 0.12:
                        inner_left = x + 3
                        break
                inner_right = rim_right
                for x in range(bottle_cx + 12, int(w * 0.76)):
                    if fg_bin[mid_y1:mid_y2, x].mean() > 0.12:
                        inner_right = x - 3
                        break

                bottle_left = max(rim_left - 4, inner_left)
                bottle_right = min(rim_right + 4, inner_right)
                half_w = max(int(w * 0.055), (bottle_right - bottle_left) // 2)
                bottle_cx = (bottle_left + bottle_right) // 2
                bottle_left = bottle_cx - half_w
                bottle_right = bottle_cx + half_w
                bottle_w = bottle_right - bottle_left

                cap_extension = int(bottle_w * 0.62)
                bottle_top = max(int(h * 0.08), y_logo_top - cap_extension)
                bottle_bot = min(int(h * 0.88), y_base_bot + 4)
                bottle_h = bottle_bot - bottle_top

                new_mask = Image.new("L", (w, h), 0)
                m_draw = ImageDraw.Draw(new_mask)

                cap_h = int(bottle_h * 0.19)
                cap_inset = int(bottle_w * 0.05)
                shoulder_y = bottle_top + cap_h

                m_draw.rounded_rectangle(
                    [bottle_left, shoulder_y - int(cap_h * 0.25), bottle_right, bottle_bot],
                    radius=max(12, int(bottle_w * 0.18)),
                    fill=255,
                )
                m_draw.rounded_rectangle(
                    [bottle_left + cap_inset, bottle_top, bottle_right - cap_inset, shoulder_y + int(cap_h * 0.2)],
                    radius=max(8, int(bottle_w * 0.10)),
                    fill=255,
                )
                new_mask = new_mask.filter(ImageFilter.GaussianBlur(radius=1.5))
                new_mask_np = np.asarray(new_mask, dtype=np.uint8)

                out_rgb = rgb.copy()
                xs_grid = np.arange(w, dtype=np.float32)[np.newaxis, :]
                ys_grid = np.arange(h, dtype=np.float32)[:, np.newaxis]
                rel_x = (xs_grid - bottle_cx) / max(1.0, float(half_w))
                cyl_shade = np.clip((rel_x + 0.15) ** 2, 0.0, 1.4)

                shade_r = 250.0 - 24.0 * cyl_shade
                shade_g = 251.0 - 22.0 * cyl_shade
                shade_b = 253.0 - 18.0 * cyl_shade

                seam_dist = np.abs(ys_grid - shoulder_y)
                seam_darken = np.where(seam_dist < 3.5, 14.0 * (1.0 - seam_dist / 3.5), 0.0)

                in_bottle = new_mask_np > 20
                side_clutter = (
                    in_bottle
                    & (ys_grid > (y_logo_top + int(bottle_h * 0.14)))
                    & (ys_grid < (y_base_bot - 14))
                    & (np.abs(rel_x) > 0.35)
                    & (gray < 215)
                )
                for ch, shade_ch in enumerate((shade_r, shade_g, shade_b)):
                    target_val = shade_ch - seam_darken
                    out_rgb[:, :, ch] = np.where(side_clutter, target_val, out_rgb[:, :, ch])
                    blend = np.clip((gray - 215.0) / 35.0, 0.0, 1.0) * (new_mask_np / 255.0)
                    out_rgb[:, :, ch] = out_rgb[:, :, ch] * (1.0 - blend) + target_val * blend

                reconstructed_rgba = Image.fromarray(np.clip(out_rgb, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
                reconstructed_rgba.putalpha(new_mask)
                return reconstructed_rgba, new_mask_np

    out = rgba_img.copy()
    out.putalpha(Image.fromarray(mask_arr, mode="L"))
    return out, mask_arr


def _remove_background_edge_aware_fallback(img: Image.Image) -> Image.Image:
    """
    Upgraded pure-Pillow edge-stopped, multi-seed border flood-fill with interior hole filling.
    Used only if ONNX Runtime is unavailable.
    """
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    work_max = 360
    scale = min(work_max / orig_w, work_max / orig_h, 1.0)
    ww = max(32, int(orig_w * scale))
    wh = max(32, int(orig_h * scale))
    small = rgba.resize((ww, wh), Image.Resampling.BILINEAR)
    px = small.load()

    # Compute edge barrier map so flood-fill stops at subtle object contours (including white-on-white edges)
    gray_small = small.convert("L")
    edges = gray_small.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    edge_px = edges.load()

    def color_dist(c1, c2):
        dr = c1[0] - c2[0]
        dg = c1[1] - c2[1]
        db = c1[2] - c2[2]
        return (0.30 * dr * dr + 0.59 * dg * dg + 0.11 * db * db) ** 0.5

    bg_mask = [[False] * ww for _ in range(wh)]
    queue = deque()

    # Seed from outer borders, carrying each seed's own local border color (sr, sg, sb)
    step = max(1, min(ww, wh) // 40)
    for x in range(0, ww, step):
        for sy in (0, wh - 1):
            if not bg_mask[sy][x]:
                sc = px[x, sy][:3]
                bg_mask[sy][x] = True
                queue.append((x, sy, sc))
    for y in range(0, wh, step):
        for sx in (0, ww - 1):
            if not bg_mask[y][sx]:
                sc = px[sx, y][:3]
                bg_mask[y][sx] = True
                queue.append((sx, y, sc))

    local_step_thresh = 11.5
    seed_thresh = 30.0
    edge_barrier = 26
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    bg_count = len(queue)

    while queue:
        cx, cy, seed_c = queue.popleft()
        cur_c = px[cx, cy][:3]
        for dx, dy in neighbors:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < ww and 0 <= ny < wh and not bg_mask[ny][nx]:
                if edge_px[nx, ny] > edge_barrier:
                    continue
                nc = px[nx, ny][:3]
                if color_dist(cur_c, nc) <= local_step_thresh and color_dist(seed_c, nc) <= seed_thresh:
                    bg_mask[ny][nx] = True
                    bg_count += 1
                    queue.append((nx, ny, seed_c))

    fg_ratio = 1.0 - (bg_count / float(ww * wh))
    if fg_ratio < 0.03 or fg_ratio > 0.97:
        return rgba

    mask_small = Image.new("L", (ww, wh), 255)
    m_px = mask_small.load()
    for y in range(wh):
        row = bg_mask[y]
        for x in range(ww):
            if row[x]:
                m_px[x, y] = 0

    mask_full = mask_small.resize((orig_w, orig_h), Image.Resampling.BILINEAR)
    mask_full = mask_full.filter(ImageFilter.GaussianBlur(radius=1.5))
    mask_full = mask_full.point(lambda a: 0 if a < 28 else (255 if a > 225 else int((a - 28) * 255 / 197)))

    out = rgba.copy()
    out.putalpha(mask_full)
    return out


def _remove_background_smart(img: Image.Image) -> Image.Image:
    """
    Primary AI + Computer Vision studio background segmentation pipeline:
    1. Dual-Pass U2Netp Deep Learning Salient Object Detection (natural RGB + local contrast/highlight enhanced).
    2. Connected-Component Center Subject Selection & Peripheral Room Clutter Rejection.
    3. White/Bright Product Hollow-Body Detection & 3D Studio Cylinder Reconstruction.
    4. Soft Alpha Matting & Edge Feathering.
    """
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    sess = _ensure_ai_runtime()
    if sess is not None:
        try:
            import numpy as np

            rgb = rgba.convert("RGB")
            # Pass 1: Natural RGB U2Netp salience
            pred1 = _run_u2net_pass(sess, rgb)

            # Pass 2: Local contrast & highlight edge boosted pass (helps white-on-light products)
            boosted = ImageOps.autocontrast(rgb, cutoff=1)
            boosted = ImageEnhance.Contrast(boosted).enhance(1.35)
            boosted = boosted.filter(ImageFilter.UnsharpMask(radius=4, percent=180, threshold=2))
            pred2 = _run_u2net_pass(sess, boosted)

            # Combine passes with a soft center framing prior
            yy, xx = np.mgrid[0:320, 0:320]
            dist_center = (((xx - 160.0) / 160.0) ** 2 + ((yy - 154.0) / 160.0) ** 2) ** 0.5
            center_prior = np.clip(1.12 - 0.42 * dist_center, 0.35, 1.05).astype(np.float32)

            combined = np.maximum(pred1, pred2 * 0.88) * center_prior
            c_min, c_max = float(combined.min()), float(combined.max())
            if c_max - c_min > 1e-6:
                combined = (combined - c_min) / (c_max - c_min)

            cleaned_320 = _filter_central_components_and_fill_holes(combined)
            mask_u8_small = Image.fromarray(np.clip(cleaned_320 * 255.0, 0, 255).astype(np.uint8), mode="L")
            mask_full = mask_u8_small.resize((orig_w, orig_h), Image.Resampling.BICUBIC)
            mask_full = mask_full.filter(ImageFilter.GaussianBlur(radius=1.4))
            mask_full = mask_full.point(lambda a: 0 if a < 36 else (255 if a > 215 else int((a - 36) * 255 / 179)))
            mask_np = np.asarray(mask_full, dtype=np.uint8)

            out, _ = _reconstruct_white_product_if_hollow(rgba, mask_np)
            return out
        except Exception as e:
            logger.warning("U2Net segmentation fallback triggered: %s", e)

    out_fb = _remove_background_edge_aware_fallback(rgba)
    try:
        import numpy as np
        mask_np = np.asarray(out_fb.getchannel("A"), dtype=np.uint8)
        out_fb, _ = _reconstruct_white_product_if_hollow(out_fb, mask_np)
    except Exception:
        pass
    return out_fb


def _create_studio_stage(target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """Creates a professional photography studio backdrop with subtle radial spotlight."""
    if bg_style == "studio_dark":
        base_col = (6, 10, 20, 255)
        center_col = (24, 38, 62, 255)
        horizon_col = (12, 18, 34, 255)
    else:
        base_col = (232, 237, 244, 255)
        center_col = (252, 253, 255, 255)
        horizon_col = (240, 244, 249, 255)

    stage = Image.new("RGBA", (target_size, target_size), base_col)

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

    floor = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    f_draw = ImageDraw.Draw(floor)
    floor_y = int(target_size * 0.78)
    f_draw.rectangle([0, floor_y, target_size, target_size], fill=(horizon_col[0], horizon_col[1], horizon_col[2], 150))
    floor = floor.filter(ImageFilter.GaussianBlur(radius=max(6, target_size // 35)))
    stage = Image.alpha_composite(stage, floor)

    return stage


def _apply_raqamiyat_branding(canvas: Image.Image, target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """Applies the official Raqamiyat logo & verified studio hallmark cleanly."""
    if os.path.exists(EMBLEM_PATH):
        try:
            emblem = Image.open(EMBLEM_PATH).convert("RGBA")
            emb_size = max(44, int(target_size * 0.10))
            emblem_resized = emblem.resize((emb_size, emb_size), Image.Resampling.LANCZOS)
            pad = int(target_size * 0.035)
            canvas.paste(emblem_resized, (target_size - emb_size - pad, pad), emblem_resized)
        except Exception as ee:
            logger.warning("Could not apply emblem: %s", ee)

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
    2. Deep Learning AI + CV Background Isolation: Uses U2Netp Salient Object Detection,
       Connected-Component Center Subject Filtering, and 3D White-Product Reconstruction.
    3. 3D Silhouette Drop Shadow & Studio Stage: Ensures both dark and pure-white products
       stand out with razor-sharp 3D studio depth.
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

        max_dim = 1400
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        if isolate_white:
            if _has_meaningful_alpha(img):
                # Even if client sent an alpha cutout (e.g. Android ML Kit), clean peripheral
                # clutter and reconstruct white product bodies if ML Kit hollowed them out!
                try:
                    import numpy as np
                    alpha_np = np.asarray(img.getchannel("A"), dtype=np.uint8)
                    alpha_320 = Image.fromarray(alpha_np, mode="L").resize((320, 320), Image.Resampling.BILINEAR)
                    cleaned_320 = _filter_central_components_and_fill_holes(np.asarray(alpha_320, dtype=np.float32) / 255.0)
                    cleaned_full = Image.fromarray(np.clip(cleaned_320 * 255.0, 0, 255).astype(np.uint8), mode="L").resize(
                        img.size, Image.Resampling.BICUBIC
                    )
                    img, _ = _reconstruct_white_product_if_hollow(img, np.asarray(cleaned_full, dtype=np.uint8))
                except Exception as e:
                    logger.warning("Alpha refinement fallback: %s", e)
            else:
                img = _remove_background_smart(img)

            alpha = img.getchannel("A")
            bbox = alpha.point(lambda a: 255 if a > 24 else 0).getbbox()
            if bbox:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                if bw > 20 and bh > 20:
                    img = img.crop(bbox)

            w, h = img.size
            canvas = _create_studio_stage(target_size, bg_style=bg_style)

            max_prod_w = int(target_size * 0.72)
            max_prod_h = int(target_size * 0.66)
            scale = min(max_prod_w / w, max_prod_h / h)
            nw = max(16, int(w * scale))
            nh = max(16, int(h * scale))
            resized_prod = img.resize((nw, nh), Image.Resampling.LANCZOS)

            # Adaptive Studio Polish: avoid blowing out highlights on white products
            r, g, b, a = resized_prod.split()
            rgb_prod = Image.merge("RGB", (r, g, b))
            rgb_prod = ImageEnhance.Sharpness(rgb_prod).enhance(1.18)
            rgb_prod = ImageEnhance.Color(rgb_prod).enhance(1.05)
            r2, g2, b2 = rgb_prod.split()
            resized_prod = Image.merge("RGBA", (r2, g2, b2, a))

            px = (target_size - nw) // 2
            py = int(target_size * 0.43) - (nh // 2)
            py = max(int(target_size * 0.06), py)

            # 1. 360-degree 3D Silhouette Ambient Drop Shadow (crucial so white products pop on white studio stage)
            sil_shadow = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            sil_layer = Image.new("RGBA", (nw, nh), (15, 23, 42, 255))
            sil_layer.putalpha(a.point(lambda v: int(v * (0.25 if bg_style == "studio_white" else 0.45))))
            sil_shadow.paste(sil_layer, (px, py + 7), sil_layer)
            sil_shadow = sil_shadow.filter(ImageFilter.GaussianBlur(radius=max(10, target_size // 55)))
            canvas = Image.alpha_composite(canvas, sil_shadow)

            # 2. Multi-layer realistic floor contact shadow directly under product base
            shadow = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            shadow_w = max(28, int(nw * 0.80))
            shadow_h = max(12, int(target_size * 0.042))
            sx1 = (target_size - shadow_w) // 2
            sy1 = min(target_size - shadow_h - 40, py + nh - (shadow_h // 2))
            s_draw.ellipse([sx1, sy1, sx1 + shadow_w, sy1 + shadow_h], fill=(15, 23, 42, 52))
            core_w = int(shadow_w * 0.58)
            core_h = max(6, shadow_h // 2)
            cx1 = (target_size - core_w) // 2
            cy1 = sy1 + (shadow_h - core_h) // 2
            s_draw.ellipse([cx1, cy1, cx1 + core_w, cy1 + core_h], fill=(15, 23, 42, 75))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(6, shadow_h // 2)))
            canvas = Image.alpha_composite(canvas, shadow)

            # 3. Composite isolated product
            canvas.paste(resized_prod, (px, py), resized_prod)
        else:
            w, h = img.size
            min_side = min(w, h)
            crop_x = (w - min_side) // 2
            crop_y = (h - min_side) // 2
            square_img = img.crop((crop_x, crop_y, crop_x + min_side, crop_y + min_side))
            canvas = square_img.resize((target_size, target_size), Image.Resampling.LANCZOS)
            canvas = ImageEnhance.Contrast(canvas).enhance(1.06)
            canvas = ImageEnhance.Sharpness(canvas).enhance(1.18)

        if add_hallmark:
            canvas = _apply_raqamiyat_branding(canvas, target_size, bg_style=bg_style)

        final_img = canvas.convert("RGB")
        buf = io.BytesIO()
        final_img.save(buf, format="JPEG", quality=94, optimize=True)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.error("Error in process_camera_product_snapshot: %s", e)
        raise
