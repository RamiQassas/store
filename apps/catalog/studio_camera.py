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
    for lbl, (sc, mx, my, area, cf) in comp_scores.items():
        if lbl == best_label:
            continue
        horiz_dist = abs(mx - best_x) / float(w)
        if cf > 0.55 and horiz_dist < 0.14 and sc >= best_score * 0.08:
            keep_mask |= (labels == lbl)

    cleaned = np.where(keep_mask, mask_320, 0.0).astype(np.float32)

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


def _regularize_contour_envelope(mask_pil: Image.Image) -> Image.Image:
    """
    Applies 1D subpixel contour envelope smoothing along the left and right vertical profiles
    of the isolated product. Shaves off outward background bumps/shadow protrusions and
    eliminates 320x320 neural staircase waviness while preserving narrower caps and necks.
    """
    try:
        import numpy as np

        arr = np.asarray(mask_pil, dtype=np.float32)
        h, w = arr.shape
        fg = arr > 110
        row_has = fg.any(axis=1)
        ys = np.where(row_has)[0]
        if len(ys) < 24:
            return mask_pil

        y0, y1 = int(ys[0]), int(ys[-1])
        fh = y1 - y0 + 1
        x_left = np.zeros(fh, dtype=np.float32)
        x_right = np.zeros(fh, dtype=np.float32)
        for i, y in enumerate(range(y0, y1 + 1)):
            xs = np.where(fg[y])[0]
            x_left[i] = float(xs[0])
            x_right[i] = float(xs[-1])

        win = max(15, int(fh * 0.30))
        half = win // 2
        reg_left = np.copy(x_left)
        reg_right = np.copy(x_right)
        for i in range(fh):
            s = max(0, i - half)
            e = min(fh, i + half + 1)
            reg_left[i] = np.percentile(x_left[s:e], 68)
            reg_right[i] = np.percentile(x_right[s:e], 32)

        sigma = max(3.0, fh * 0.04)
        k_rad = int(sigma * 2.5)
        kx = np.arange(-k_rad, k_rad + 1, dtype=np.float32)
        kernel = np.exp(-(kx ** 2) / (2.0 * sigma * sigma))
        kernel /= kernel.sum()

        smooth_left = np.convolve(np.pad(reg_left, k_rad, mode="edge"), kernel, mode="valid")
        smooth_right = np.convolve(np.pad(reg_right, k_rad, mode="edge"), kernel, mode="valid")

        final_left = np.maximum(x_left, smooth_left)
        final_right = np.minimum(x_right, smooth_right)

        k2_rad = max(2, int(fh * 0.02))
        kx2 = np.arange(-k2_rad, k2_rad + 1, dtype=np.float32)
        k2 = np.exp(-(kx2 ** 2) / (2.0 * (k2_rad * 0.6) ** 2))
        k2 /= k2.sum()
        final_left = np.convolve(np.pad(final_left, k2_rad, mode="edge"), k2, mode="valid")
        final_right = np.convolve(np.pad(final_right, k2_rad, mode="edge"), k2, mode="valid")

        out_mask = np.zeros((h, w), dtype=np.uint8)
        grid_x = np.arange(w, dtype=np.float32)
        for i, y in enumerate(range(y0, y1 + 1)):
            l_val = final_left[i]
            r_val = final_right[i]
            if r_val > l_val + 4:
                alpha_l = np.clip((grid_x - l_val + 1.0) / 1.8, 0.0, 1.0)
                alpha_r = np.clip((r_val - grid_x + 1.0) / 1.8, 0.0, 1.0)
                row_a = np.minimum(alpha_l, alpha_r) * (arr[y] / 255.0)
                solid_span = (grid_x >= l_val + 1.2) & (grid_x <= r_val - 1.2)
                row_a = np.where(solid_span, np.maximum(row_a, 1.0), row_a)
                out_mask[y] = np.clip(row_a * 255.0, 0, 255).astype(np.uint8)

        return Image.fromarray(out_mask, mode="L")
    except Exception:
        return mask_pil


def _refine_product_edges_and_dehalo(rgba_img: Image.Image, mask_pil: Image.Image) -> Image.Image:
    """
    Eliminates wavy 320x320 neural mask stair-stepping and dark/grey room edge halos:
    1. Smooths contour curvature with MedianFilter + 1D subpixel envelope regularization.
    2. Chokes the mask edge inward by ~1.5px to shave off external background fringe.
    3. Performs RGB Edge Color Decontamination: replaces the outer 3px boundary RGB
       with clean interior product colors so zero dark background halo remains.
    """
    w, h = rgba_img.size
    m = mask_pil.resize((w, h), Image.Resampling.BICUBIC)
    m = m.filter(ImageFilter.MedianFilter(size=5))
    m_eroded = m.filter(ImageFilter.MinFilter(size=3))
    m = Image.blend(m, m_eroded, 0.60)
    m = _regularize_contour_envelope(m)
    m = m.filter(ImageFilter.GaussianBlur(radius=1.5))
    m = m.point(lambda a: 0 if a < 72 else (255 if a > 218 else int((a - 72) * 255 / 146)))

    try:
        import numpy as np

        rgb_orig = rgba_img.convert("RGB")
        rgb_interior = rgb_orig.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
        orig_np = np.asarray(rgb_orig, dtype=np.float32)
        int_np = np.asarray(rgb_interior, dtype=np.float32)
        alpha_np = np.asarray(m, dtype=np.float32) / 255.0

        is_edge = ((alpha_np > 0.02) & (alpha_np < 0.92))[:, :, np.newaxis]
        clean_np = np.where(is_edge, 0.35 * orig_np + 0.65 * int_np, orig_np)
        out = Image.fromarray(np.clip(clean_np, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
        out.putalpha(m)
        return out
    except Exception:
        out = rgba_img.copy()
        out.putalpha(m)
        return out


def _reconstruct_white_product_if_hollow(rgba_img: Image.Image, mask_arr):
    """
    Handles overexposed white/bright containers photographed against bright walls
    where segmentation only captured interior markings (logo + bottom rim).
    """
    import numpy as np

    h, w = mask_arr.shape
    white_bg = Image.new("RGBA", (w, h), (250, 251, 253, 255))
    comp_rgb_img = Image.alpha_composite(white_bg, rgba_img.convert("RGBA")).convert("RGB")
    rgb = np.asarray(comp_rgb_img, dtype=np.float32)
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    dark_markings = gray < 205
    fg_bin = (mask_arr > 80) | dark_markings

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

    refined = _refine_product_edges_and_dehalo(rgba_img, Image.fromarray(mask_arr, mode="L"))
    return refined, np.asarray(refined.getchannel("A"), dtype=np.uint8)


def _apply_studio_relighting(prod_rgba: Image.Image) -> Image.Image:
    """
    Commercial Studio Softbox Relighting & Color Grading (applied strictly to isolated product):
    - Automatically lifts dim indoor phone exposure (gamma & white-point normalization).
    - Adds a subtle 3D vertical studio softbox specular sheen along the product surface.
    - Enhances micro-contrast and typography sharpness (UnsharpMask).
    """
    r, g, b, a = prod_rgba.split()
    rgb_img = Image.merge("RGB", (r, g, b))

    try:
        import numpy as np

        rgb = np.asarray(rgb_img, dtype=np.float32)
        alpha_np = np.asarray(a, dtype=np.float32) / 255.0
        fg_mask = alpha_np > 0.5

        if fg_mask.sum() > 50:
            lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
            fg_lum = lum[fg_mask]
            p50 = float(np.percentile(fg_lum, 50))
            p92 = float(np.percentile(fg_lum, 92))

            # 1. White-point & exposure normalization if indoor photo is under-lit
            gain = 1.0
            if p92 < 238.0 and p92 > 40.0:
                gain = min(1.26, 242.0 / p92)
            gamma = 1.0
            if p50 * gain < 155.0:
                gamma = max(0.76, min(0.94, (p50 * gain) / 168.0))

            norm = np.clip((rgb * gain) / 255.0, 0.0, 1.0)
            if gamma < 0.99:
                norm = norm ** gamma

            # Gentle S-curve for studio pop without clipping white highlights
            norm = np.clip(0.5 + (norm - 0.5) * 1.08, 0.0, 1.0)

            # 2. Subtle 3D vertical softbox reflection highlight along left-center of product
            h, w, _ = rgb.shape
            xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[np.newaxis, :, np.newaxis]
            softbox_sheen = 1.0 + 0.055 * np.exp(-((xs - 0.36) ** 2) / (2.0 * (0.18 ** 2)))
            norm = np.clip(norm * softbox_sheen, 0.0, 1.0)

            rgb_img = Image.fromarray((norm * 255.0).astype(np.uint8), mode="RGB")
    except Exception as e:
        logger.debug("Studio relighting fallback: %s", e)

    rgb_img = ImageEnhance.Color(rgb_img).enhance(1.12)
    rgb_img = rgb_img.filter(ImageFilter.UnsharpMask(radius=1.8, percent=135, threshold=2))
    r2, g2, b2 = rgb_img.split()
    return Image.merge("RGBA", (r2, g2, b2, a))


def _remove_background_edge_aware_fallback(img: Image.Image) -> Image.Image:
    """
    Upgraded pure-Pillow edge-stopped, multi-seed border flood-fill with interior hole filling.
    """
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    work_max = 360
    scale = min(work_max / orig_w, work_max / orig_h, 1.0)
    ww = max(32, int(orig_w * scale))
    wh = max(32, int(orig_h * scale))
    small = rgba.resize((ww, wh), Image.Resampling.BILINEAR)
    px = small.load()

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

    return _refine_product_edges_and_dehalo(rgba, mask_small)


def _remove_background_smart(img: Image.Image) -> Image.Image:
    """
    Primary AI + Computer Vision studio background segmentation pipeline.
    """
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    sess = _ensure_ai_runtime()
    if sess is not None:
        try:
            import numpy as np

            rgb = rgba.convert("RGB")
            pred1 = _run_u2net_pass(sess, rgb)

            boosted = ImageOps.autocontrast(rgb, cutoff=1)
            boosted = ImageEnhance.Contrast(boosted).enhance(1.35)
            boosted = boosted.filter(ImageFilter.UnsharpMask(radius=4, percent=180, threshold=2))
            pred2 = _run_u2net_pass(sess, boosted)

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
    """
    Creates a seamless, artifact-free 3D photography studio cyclorama backdrop.
    Uses a continuous 2D mathematical lighting shader so there is zero black alpha-blur bleeding.
    """
    try:
        import numpy as np

        yy, xx = np.mgrid[0:target_size, 0:target_size].astype(np.float32)
        nx = (xx - target_size * 0.50) / (target_size * 0.50)
        ny = (yy - target_size * 0.42) / (target_size * 0.50)
        rad = np.sqrt(nx ** 2 + ny ** 2)
        spot = np.clip(1.0 - (rad / 1.35) ** 1.6, 0.0, 1.0)

        # Smooth cyclorama floor curve below y = 70%
        floor_t = np.clip((yy / target_size - 0.68) / 0.32, 0.0, 1.0)
        horizon_dip = np.exp(-(((yy / target_size) - 0.74) ** 2) / (2.0 * (0.045 ** 2)))

        if bg_style == "studio_dark":
            r = 8.0 + 22.0 * spot - 4.0 * horizon_dip + 6.0 * (floor_t ** 1.4)
            g = 13.0 + 34.0 * spot - 6.0 * horizon_dip + 10.0 * (floor_t ** 1.4)
            b = 26.0 + 58.0 * spot - 8.0 * horizon_dip + 18.0 * (floor_t ** 1.4)
        else:
            # Pure luxury porcelain studio stage: (255,255,255) center -> (238,242,248) outer corners
            # with a whisper-soft studio floor horizon reflection
            r = 238.0 + 17.0 * spot - 6.0 * horizon_dip - 3.0 * (floor_t ** 1.5)
            g = 242.0 + 13.0 * spot - 5.0 * horizon_dip - 2.0 * (floor_t ** 1.5)
            b = 248.0 + 7.0 * spot - 3.0 * horizon_dip - 1.0 * (floor_t ** 1.5)

        rgb = np.stack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255)], axis=-1).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB").convert("RGBA")
    except Exception:
        base_col = (10, 15, 28, 255) if bg_style == "studio_dark" else (246, 248, 252, 255)
        return Image.new("RGBA", (target_size, target_size), base_col)


def _paste_soft_shadow_from_alpha(
    canvas: Image.Image,
    alpha_mask: Image.Image,
    pos: tuple,
    shadow_rgb: tuple = (15, 23, 42),
    opacity_scale: float = 0.25,
    blur_radius: int = 12,
) -> Image.Image:
    """
    Renders a physically accurate soft shadow by blurring ONLY the 'L' alpha channel
    and filling RGB with shadow_rgb, avoiding Pillow's RGBA (0,0,0,0) blur artifact.
    """
    w, h = canvas.size
    full_alpha = Image.new("L", (w, h), 0)
    scaled_a = alpha_mask.point(lambda v: int(min(255, v * opacity_scale)))
    full_alpha.paste(scaled_a, pos)
    full_alpha = full_alpha.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    shadow_layer = Image.new("RGBA", (w, h), (shadow_rgb[0], shadow_rgb[1], shadow_rgb[2], 0))
    shadow_layer.putalpha(full_alpha)
    return Image.alpha_composite(canvas, shadow_layer)


def _apply_raqamiyat_branding(canvas: Image.Image, target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """Applies the official Raqamiyat 3D luxury emblem & compact studio hallmark cleanly."""
    # 1. Top-right subtle luxury emblem watermark
    if os.path.exists(EMBLEM_PATH):
        try:
            emblem = Image.open(EMBLEM_PATH).convert("RGBA")
            emb_size = max(42, int(target_size * 0.088))
            emblem_resized = emblem.resize((emb_size, emb_size), Image.Resampling.LANCZOS)
            pad = int(target_size * 0.032)
            ex = target_size - emb_size - pad
            ey = pad
            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                emblem_resized.getchannel("A"),
                (ex, ey + 3),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.22 if bg_style == "studio_white" else 0.50,
                blur_radius=6,
            )
            canvas.paste(emblem_resized, (ex, ey), emblem_resized)
        except Exception as ee:
            logger.warning("Could not apply emblem: %s", ee)

    # 2. Bottom centered compact official Raqamiyat master badge
    if os.path.exists(MASTER_BADGE_PATH):
        try:
            badge = Image.open(MASTER_BADGE_PATH).convert("RGBA")
            target_bw = int(target_size * 0.46)
            target_bh = max(16, int(badge.height * (target_bw / badge.width)))
            badge_resized = badge.resize((target_bw, target_bh), Image.Resampling.LANCZOS)

            bx = (target_size - target_bw) // 2
            by = target_size - target_bh - int(target_size * 0.028)

            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                badge_resized.getchannel("A"),
                (bx, by + 4),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.28 if bg_style == "studio_white" else 0.60,
                blur_radius=8,
            )
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
    Transforms a raw mobile camera product photo into an ultra-luxury e-commerce studio shot:
    1. EXIF Auto-Orientation: Fixes mobile camera rotation.
    2. Deep Learning AI + Edge De-Haloing Isolation: U2Netp Salient Object Detection,
       Contour Curvature Smoothing, and RGB Edge Color Decontamination.
    3. Studio Softbox Relighting: Lifts dim indoor phone lighting & adds 3D softbox sheen.
    4. Seamless Cyclorama Stage & Multi-Layer Contact Shadow.
    5. Official Raqamiyat 3D Luxury Branding.
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
            bbox = alpha.point(lambda a: 255 if a > 32 else 0).getbbox()
            if bbox:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                if bw > 20 and bh > 20:
                    img = img.crop(bbox)

            w, h = img.size
            canvas = _create_studio_stage(target_size, bg_style=bg_style)

            # Generous hero product sizing (up to 73% height, 75% width)
            max_prod_w = int(target_size * 0.75)
            max_prod_h = int(target_size * 0.72)
            scale = min(max_prod_w / w, max_prod_h / h)
            nw = max(16, int(w * scale))
            nh = max(16, int(h * scale))
            resized_prod = img.resize((nw, nh), Image.Resampling.LANCZOS)

            # Studio Softbox Relighting & Clarity Polish
            resized_prod = _apply_studio_relighting(resized_prod)
            prod_alpha = resized_prod.getchannel("A")

            px = (target_size - nw) // 2
            py = int(target_size * 0.435) - (nh // 2)
            py = max(int(target_size * 0.045), py)

            # 1. Soft 360-degree 3D Silhouette Ambient Drop Shadow (zero black-bleed artifact)
            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                prod_alpha,
                (px, py + 6),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.16 if bg_style == "studio_white" else 0.42,
                blur_radius=max(12, target_size // 48),
            )

            # 2. Grounding Studio Floor Contact Shadow directly under product base
            shadow_w = max(32, int(nw * 0.84))
            shadow_h = max(14, int(target_size * 0.038))
            sx1 = (target_size - shadow_w) // 2
            sy1 = min(target_size - shadow_h - 46, py + nh - (shadow_h // 2))

            floor_alpha = Image.new("L", (target_size, target_size), 0)
            fa_draw = ImageDraw.Draw(floor_alpha)
            fa_draw.ellipse([sx1, sy1, sx1 + shadow_w, sy1 + shadow_h], fill=55)
            core_w = int(shadow_w * 0.56)
            core_h = max(6, shadow_h // 2)
            cx1 = (target_size - core_w) // 2
            cy1 = sy1 + (shadow_h - core_h) // 2
            fa_draw.ellipse([cx1, cy1, cx1 + core_w, cy1 + core_h], fill=95)
            floor_alpha = floor_alpha.filter(ImageFilter.GaussianBlur(radius=max(7, shadow_h // 2)))

            floor_shadow = Image.new("RGBA", (target_size, target_size), (15, 23, 42, 0))
            floor_shadow.putalpha(floor_alpha)
            canvas = Image.alpha_composite(canvas, floor_shadow)

            # 3. Composite isolated & relit product
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
