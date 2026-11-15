import io
import os
import sys
import logging
import threading
import subprocess
from collections import deque
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageDraw
from django.conf import settings

logger = logging.getLogger(__name__)

MASTER_BADGE_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_master_badge.png")
EMBLEM_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "raqamiyat_emblem.png")
U2NETP_ONNX_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "u2netp.onnx")
ISNET_ONNX_PATH = os.path.join(settings.BASE_DIR, "apps", "catalog", "assets", "isnet-general-use.onnx")

U2NETP_FALLBACK_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
ISNET_FALLBACK_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"

_ORT_SESSION = None
_ORT_ISNET_SESSION = None
_ORT_INIT_ATTEMPTED = False
_ISNET_DOWNLOAD_STARTED = False


def _download_isnet_in_background():
    """Downloads the 1024x1024 IS-Net e-commerce segmentation model in the background if not present."""
    global _ORT_ISNET_SESSION
    try:
        if not os.path.exists(ISNET_ONNX_PATH) or os.path.getsize(ISNET_ONNX_PATH) < 50_000_000:
            os.makedirs(os.path.dirname(ISNET_ONNX_PATH), exist_ok=True)
            import requests

            tmp_path = ISNET_ONNX_PATH + ".tmp"
            with requests.get(ISNET_FALLBACK_URL, stream=True, timeout=60) as r:
                if r.status_code == 200:
                    with open(tmp_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 512):
                            if chunk:
                                f.write(chunk)
                    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 50_000_000:
                        os.replace(tmp_path, ISNET_ONNX_PATH)

        if os.path.exists(ISNET_ONNX_PATH) and os.path.getsize(ISNET_ONNX_PATH) > 50_000_000:
            import onnxruntime as ort

            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 2
            sess_opts.inter_op_num_threads = 1
            _ORT_ISNET_SESSION = ort.InferenceSession(
                ISNET_ONNX_PATH,
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )
            logger.info("Loaded 1024x1024 IS-Net high-precision segmentation model for Studio Camera.")
    except Exception as e:
        logger.debug("Background IS-Net download/init skipped: %s", e)


def _ensure_ai_runtime():
    """
    Lazily loads the ONNX Runtime session for Salient Object & Dichotomous Image Segmentation.
    Uses 1024x1024 IS-Net when available on disk, and 320x320 U2Netp as immediate fast model.
    """
    global _ORT_SESSION, _ORT_ISNET_SESSION, _ORT_INIT_ATTEMPTED, _ISNET_DOWNLOAD_STARTED
    if not _ISNET_DOWNLOAD_STARTED:
        _ISNET_DOWNLOAD_STARTED = True
        threading.Thread(target=_download_isnet_in_background, daemon=True).start()

    if _ORT_ISNET_SESSION is not None:
        return _ORT_ISNET_SESSION, "isnet"
    if _ORT_SESSION is not None:
        return _ORT_SESSION, "u2netp"
    if _ORT_INIT_ATTEMPTED:
        return None, None
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
            return None, None

    try:
        if os.path.exists(ISNET_ONNX_PATH) and os.path.getsize(ISNET_ONNX_PATH) > 50_000_000:
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 2
            sess_opts.inter_op_num_threads = 1
            _ORT_ISNET_SESSION = ort.InferenceSession(
                ISNET_ONNX_PATH,
                sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )
            return _ORT_ISNET_SESSION, "isnet"
    except Exception:
        pass

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
            return _ORT_SESSION, "u2netp"
    except Exception as e:
        logger.warning("Failed initializing U2Netp ONNX session: %s", e)
    return None, None


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


def _run_ai_pass(sess, model_kind: str, rgb_img: Image.Image):
    """Runs either 1024x1024 IS-Net or 320x320 U2Netp forward pass and returns a [0..1] float32 map."""
    import numpy as np

    if model_kind == "isnet":
        inp = rgb_img.resize((1024, 1024), Image.Resampling.BILINEAR)
        arr = np.asarray(inp, dtype=np.float32) / 255.0
        arr = arr - 0.5
        tensor = np.transpose(arr, (2, 0, 1))[np.newaxis, :, :, :].astype(np.float32)
        input_name = sess.get_inputs()[0].name
        pred = sess.run(None, {input_name: tensor})[0][0, 0]
    else:
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
    and fills interior holes inside the subject body.
    """
    import numpy as np

    h, w = mask_320.shape
    binary = mask_320 > 0.32
    if not binary.any():
        return mask_320

    visited = np.zeros((h, w), dtype=bool)
    labels = np.zeros((h, w), dtype=np.int32)
    comp_scores = {}
    cur_label = 0

    cx_ideal, cy_ideal = w * 0.50, h * 0.48
    core_x1, core_x2 = int(w * 0.26), int(w * 0.74)
    core_y1, core_y2 = int(h * 0.16), int(h * 0.84)

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

                if core_fraction < 0.14 and dist_norm > 0.25:
                    continue
                if touches_outer_edge and core_fraction < 0.32:
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
        # Keep vertically aligned parts of the same product (e.g. top arch/text of white packaging)
        if (cf > 0.35 and horiz_dist < 0.22 and sc >= best_score * 0.015) or (
            horiz_dist < 0.16 and 0.08 * h <= my <= 0.88 * h and area >= 18
        ):
            keep_mask |= labels == lbl

    cleaned = np.where(keep_mask, mask_320, 0.0).astype(np.float32)

    fg_solid = cleaned > 0.28
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


def _remove_bottom_display_stand(mask_arr):
    """
    Detects and removes physical display stands, metal clip holders, or pedestals underneath
    a photographed product (such as the brass/wooden stand under the SanDisk blister card).
    Signature: in the lower 42% of the product bounding box, the horizontal span drops sharply
    from the wide product body (>= 0.72 * body_width) down to a narrow support stem (<= 0.42 * body_width).
    """
    try:
        import numpy as np

        h, w = mask_arr.shape
        fg = mask_arr > 95
        ys = np.where(fg.any(axis=1))[0]
        if len(ys) < 40:
            return mask_arr

        y0, y1 = int(ys[0]), int(ys[-1])
        fh = y1 - y0 + 1
        spans = np.zeros(fh, dtype=np.float32)
        xl_arr = np.zeros(fh, dtype=np.float32)
        xr_arr = np.zeros(fh, dtype=np.float32)
        for i, y in enumerate(range(y0, y1 + 1)):
            xs = np.where(fg[y])[0]
            if len(xs) > 0:
                xl_arr[i] = float(xs[0])
                xr_arr[i] = float(xs[-1])
                spans[i] = float(xs[-1] - xs[0])

        body_spans = spans[int(fh * 0.25) : int(fh * 0.72)]
        if len(body_spans) < 10:
            return mask_arr
        w_body = float(np.percentile(body_spans, 75))
        if w_body < 24:
            return mask_arr

        # Search in lower 42% of height for a narrow stand stem / neck
        search_start = int(fh * 0.56)
        search_end = int(fh * 0.96)
        neck_thresh = w_body * 0.44

        neck_idx = None
        for i in range(search_start, search_end):
            if spans[i] <= neck_thresh:
                # Confirm there was a wide product body above this neck
                above_max = float(np.max(spans[max(0, i - int(fh * 0.14)) : i])) if i > 4 else 0.0
                if above_max >= w_body * 0.72:
                    neck_idx = i
                    break

        if neck_idx is None:
            return mask_arr

        # Walk upward from neck_idx to find the exact flat bottom edge of the product body
        cut_idx = neck_idx
        target_full_w = float(np.percentile(spans[max(0, neck_idx - int(fh * 0.18)) : neck_idx], 85))
        for j in range(neck_idx, max(search_start - 10, neck_idx - int(fh * 0.14)), -1):
            if spans[j] >= target_full_w * 0.96:
                cut_idx = j
                break

        # Trim ~3.2% of height above cut_idx to completely shave off metal stand clips gripping the bottom edge
        clip_trim = max(7, int(fh * 0.034))
        y_cut = max(y0 + int(fh * 0.50), y0 + cut_idx - clip_trim)
        out = mask_arr.copy()
        out[y_cut:, :] = 0
        return out
    except Exception:
        return mask_arr


def _restore_white_card_margins_and_hang_hole(rgba_img: Image.Image, mask_arr):
    """
    1. When a rectangular/trapezoidal white blister card (e.g. SanDisk package) has straight
       lower walls (y in 50%..92%), but its white cardboard upper sides (y in 8%..55%) were
       indented inward because white cardboard blended into a bright wall or was clipped by
       on-device segmentation, restores the full symmetrical blister card profile.
    2. Punches out any background/skin trapped inside the top-center Euro-slot hang hole.
    """
    try:
        import numpy as np

        h, w = mask_arr.shape
        fg = mask_arr > 95
        ys = np.where(fg.any(axis=1))[0]
        if len(ys) < 40:
            return rgba_img, mask_arr

        y0, y1 = int(ys[0]), int(ys[-1])
        fh = y1 - y0 + 1
        xl = np.zeros(fh, dtype=np.float32)
        xr = np.zeros(fh, dtype=np.float32)
        for i, y in enumerate(range(y0, y1 + 1)):
            xs = np.where(fg[y])[0]
            if len(xs) > 0:
                xl[i] = float(xs[0])
                xr[i] = float(xs[-1])

        # Check lower body (52%..92% of height) for straight vertical card walls
        b_s, b_e = int(fh * 0.52), int(fh * 0.92)
        if b_e - b_s < 12:
            return rgba_img, mask_arr

        xl_bot_med = float(np.median(xl[b_s:b_e]))
        xr_bot_med = float(np.median(xr[b_s:b_e]))
        w_bot = xr_bot_med - xl_bot_med
        if w_bot < 36:
            return rgba_img, mask_arr

        std_l = float(np.std(xl[b_s:b_e]))
        std_r = float(np.std(xr[b_s:b_e]))

        white_bg = Image.new("RGBA", (w, h), (248, 249, 251, 255))
        comp_rgb = np.asarray(Image.alpha_composite(white_bg, rgba_img.convert("RGBA")).convert("RGB"), dtype=np.float32)
        lum = 0.299 * comp_rgb[:, :, 0] + 0.587 * comp_rgb[:, :, 1] + 0.114 * comp_rgb[:, :, 2]

        # Check upper half brightness (12%..48% of height)
        u_y1, u_y2 = y0 + int(fh * 0.12), y0 + int(fh * 0.48)
        u_x1, u_x2 = int(xl_bot_med + w_bot * 0.15), int(xr_bot_med - w_bot * 0.15)
        upper_bright = False
        if u_y2 > u_y1 and u_x2 > u_x1:
            upper_patch = lum[u_y1:u_y2, u_x1:u_x2]
            upper_bright = float(np.percentile(upper_patch, 75)) > 205.0

        # Check if upper sides (12%..48%) are indented compared to lower straight card walls
        u_idx1, u_idx2 = int(fh * 0.12), int(fh * 0.48)
        indent_l = float(np.median(xl[u_idx1:u_idx2]) - xl_bot_med)
        indent_r = float(xr_bot_med - np.median(xr[u_idx1:u_idx2]))

        out_rgb = comp_rgb.copy()
        out_mask = mask_arr.copy()

        # Distinguish a blister card from a narrow-capped bottle:
        # On a blister card, the indentation extends deep down to 35%..50% of height AND the upper region is bright white card
        mid_indent_l = float(np.median(xl[int(fh * 0.22) : int(fh * 0.45)]) - xl_bot_med)
        mid_indent_r = float(xr_bot_med - np.median(xr[int(fh * 0.22) : int(fh * 0.45)]))

        if upper_bright and std_l < w_bot * 0.045 and std_r < w_bot * 0.045 and (mid_indent_l > w_bot * 0.05 or mid_indent_r > w_bot * 0.05):
            # Sample clean white card color from bright pixels in upper half
            card_samples = comp_rgb[u_y1:u_y2, u_x1:u_x2][lum[u_y1:u_y2, u_x1:u_x2] > 215]
            card_col = np.median(card_samples, axis=0) if len(card_samples) > 10 else np.array([244.0, 246.0, 244.0])

            card_mask_pil = Image.new("L", (w, h), 0)
            cdraw = ImageDraw.Draw(card_mask_pil)
            # Gentle retail blister card taper in top 45% ( narrows by only ~5% at top shoulder with rounded top corners )
            top_inset = w_bot * 0.045
            corner_r = max(8, int(w_bot * 0.11))
            pts_card = [
                (xl_bot_med + top_inset + corner_r, y0 + 2),
                (xr_bot_med - top_inset - corner_r, y0 + 2),
                (xr_bot_med - top_inset, y0 + 2 + corner_r),
                (xr_bot_med, y0 + int(fh * 0.46)),
                (xr_bot_med, y1),
                (xl_bot_med, y1),
                (xl_bot_med, y0 + int(fh * 0.46)),
                (xl_bot_med + top_inset, y0 + 2 + corner_r),
            ]
            cdraw.polygon(pts_card, fill=255)
            card_mask_pil = card_mask_pil.filter(ImageFilter.GaussianBlur(radius=1.5))
            card_env = np.asarray(card_mask_pil, dtype=np.uint8)

            # Where card_env expands beyond the indented mask in the upper 60% of the card,
            # fill ONLY completely transparent outer pixels (never overwrite interior text/graphics!)
            orig_a = np.asarray(rgba_img.getchannel("A"), dtype=np.float32) / 255.0
            in_upper = np.zeros((h, w), dtype=bool)
            in_upper[y0 : y0 + int(fh * 0.62), :] = True
            need_card_fill = in_upper & (card_env > 120) & (mask_arr < 35) & (orig_a < 0.08)

            for c_i in range(3):
                out_rgb[:, :, c_i] = np.where(need_card_fill, card_col[c_i], out_rgb[:, :, c_i])
            out_mask = np.where(in_upper, np.maximum(out_mask, card_env), out_mask)

        # 2. Clean top rim smudge & punch out trapped background inside top-center blister Euro-slot hang hole
        if upper_bright:
            cx_card = int(0.5 * (xl_bot_med + xr_bot_med))
            # Clean any dark background fringe clinging to the very top edge of the white card arch
            top_rim_y2 = y0 + max(4, int(fh * 0.045))
            tr_x1 = max(0, int(cx_card - w_bot * 0.25))
            tr_x2 = min(w, int(cx_card + w_bot * 0.25))
            if top_rim_y2 > y0 and tr_x2 > tr_x1:
                rim_dark = lum[y0:top_rim_y2, tr_x1:tr_x2] < 195.0
                for c_i in range(3):
                    patch_c = out_rgb[y0:top_rim_y2, tr_x1:tr_x2, c_i]
                    out_rgb[y0:top_rim_y2, tr_x1:tr_x2, c_i] = np.where(rim_dark, card_col[c_i], patch_c)

            hh_y1 = y0 + max(4, int(fh * 0.040))
            hh_y2 = y0 + int(fh * 0.165)
            hh_x1 = max(0, int(cx_card - w_bot * 0.22))
            hh_x2 = min(w, int(cx_card + w_bot * 0.22))
            if hh_y2 > hh_y1 + 4 and hh_x2 > hh_x1 + 8:
                slot_rgb = out_rgb[hh_y1:hh_y2, hh_x1:hh_x2]
                slot_lum = lum[hh_y1:hh_y2, hh_x1:hh_x2]
                slot_sat = np.max(slot_rgb, axis=2) - np.min(slot_rgb, axis=2)
                is_hole = (slot_lum < 212.0) | ((slot_sat > 14.0) & (slot_lum < 232.0))
                if 0.05 < float(is_hole.mean()) < 0.85:
                    hole_mask = np.zeros((h, w), dtype=np.uint8)
                    hole_mask[hh_y1:hh_y2, hh_x1:hh_x2] = np.where(is_hole, 255, 0).astype(np.uint8)
                    hole_pil = (
                        Image.fromarray(hole_mask, mode="L")
                        .filter(ImageFilter.MaxFilter(5))
                        .filter(ImageFilter.GaussianBlur(1.2))
                    )
                    hole_np = np.asarray(hole_pil, dtype=np.float32) / 255.0
                    # Replace RGB inside hang-hole with clean card/stage white so zero brown/skin halo remains
                    for c_i in range(3):
                        out_rgb[:, :, c_i] = np.where(hole_np > 0.15, 246.0, out_rgb[:, :, c_i])
                    out_mask = np.clip(out_mask.astype(np.float32) * (1.0 - hole_np), 0, 255).astype(np.uint8)

        out_rgba = Image.fromarray(np.clip(out_rgb, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
        out_rgba.putalpha(Image.fromarray(out_mask, mode="L"))
        return out_rgba, out_mask
    except Exception as e:
        logger.debug("Restore white card margins fallback: %s", e)
        return rgba_img, mask_arr


def _box_filter_2d(img_2d, r: int):
    """Fast O(N) 2D box filter using cumulative sums for full-resolution Guided Filtering."""
    import numpy as np

    if r <= 0:
        return img_2d.copy()
    h, w = img_2d.shape
    padded = np.pad(img_2d, ((r, r + 1), (r, r + 1)), mode="edge")
    cs = np.cumsum(np.cumsum(padded, axis=0), axis=1)
    win_area = float((2 * r + 1) * (2 * r + 1))
    out = (
        cs[2 * r + 1 : 2 * r + 1 + h, 2 * r + 1 : 2 * r + 1 + w]
        - cs[0:h, 2 * r + 1 : 2 * r + 1 + w]
        - cs[2 * r + 1 : 2 * r + 1 + h, 0:w]
        + cs[0:h, 0:w]
    ) / win_area
    return out.astype(np.float32)


def _guided_filter_fullres(rgb_img: Image.Image, alpha_01, radius: int = 6, eps: float = 1e-3):
    """
    Full-Resolution Edge-Preserving Guided Filter (He et al.):
    Snaps coarse neural masks to 1-pixel optical edges on high-res S26 Ultra images.
    """
    import numpy as np

    rgb = np.asarray(rgb_img.convert("RGB"), dtype=np.float32) / 255.0
    I_g = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    I_c1 = rgb[:, :, 0] - rgb[:, :, 1]
    I_c2 = rgb[:, :, 2] - 0.5 * (rgb[:, :, 0] + rgb[:, :, 1])

    p = np.asarray(alpha_01, dtype=np.float32)
    mean_p = _box_filter_2d(p, radius)

    q_accum = np.zeros_like(p)
    weights = (0.55, 0.25, 0.20)
    for ch_img, w_ch in zip((I_g, I_c1, I_c2), weights):
        mean_I = _box_filter_2d(ch_img, radius)
        mean_Ip = _box_filter_2d(ch_img * p, radius)
        cov_Ip = mean_Ip - mean_I * mean_p
        mean_II = _box_filter_2d(ch_img * ch_img, radius)
        var_I = np.maximum(mean_II - mean_I * mean_I, 0.0)

        a = cov_Ip / (var_I + eps)
        b = mean_p - a * mean_I
        mean_a = _box_filter_2d(a, radius)
        mean_b = _box_filter_2d(b, radius)
        q_accum += w_ch * (mean_a * ch_img + mean_b)

    return np.clip(q_accum, 0.0, 1.0)


def _smooth_contour_non_destructive(mask_pil: Image.Image) -> Image.Image:
    """
    Shape-Faithful Subpixel Contour Anti-Aliasing:
    Removes small 2-6px jagged neural stair-steps along the product perimeter using a local
    unbiased 50th-percentile filter without ever carving rectangular or blister packages into cones.
    """
    try:
        import numpy as np

        arr = np.asarray(mask_pil, dtype=np.float32)
        h, w = arr.shape
        fg = arr > 110
        ys = np.where(fg.any(axis=1))[0]
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

        # Local unbiased median window (only ~4% of height) removes tiny stair-steps while keeping corners & straight edges
        win = max(7, min(19, int(fh * 0.045)))
        half = win // 2
        med_l = np.copy(x_left)
        med_r = np.copy(x_right)
        for i in range(fh):
            s = max(0, i - half)
            e = min(fh, i + half + 1)
            med_l[i] = np.median(x_left[s:e])
            med_r[i] = np.median(x_right[s:e])

        sigma = max(1.4, min(3.0, fh * 0.010))
        k_rad = max(2, int(sigma * 2.5))
        kx = np.arange(-k_rad, k_rad + 1, dtype=np.float32)
        kernel = np.exp(-(kx ** 2) / (2.0 * sigma * sigma))
        kernel /= kernel.sum()

        final_left = np.convolve(np.pad(med_l, k_rad, mode="edge"), kernel, mode="valid")
        final_right = np.convolve(np.pad(med_r, k_rad, mode="edge"), kernel, mode="valid")

        # Apply smoothed outer boundary while preserving interior holes (like blister hang-holes!)
        out_mask = arr.copy()
        grid_x = np.arange(w, dtype=np.float32)
        for i, y in enumerate(range(y0, y1 + 1)):
            l_val = final_left[i]
            r_val = final_right[i]
            if r_val > l_val + 4:
                env_l = np.clip((grid_x - l_val + 0.8) / 1.5, 0.0, 1.0)
                env_r = np.clip((r_val - grid_x + 0.8) / 1.5, 0.0, 1.0)
                env = np.minimum(env_l, env_r) * 255.0
                # Smooth only within 4px of the left/right outer edges; keep interior holes untouched
                near_outer = (grid_x < l_val + 4.0) | (grid_x > r_val - 4.0)
                out_mask[y] = np.where(near_outer, np.minimum(arr[y], env), arr[y])

        return Image.fromarray(np.clip(out_mask, 0, 255).astype(np.uint8), mode="L")
    except Exception:
        return mask_pil


def _refine_product_edges_and_dehalo(rgba_img: Image.Image, mask_pil: Image.Image, run_guided: bool = True) -> Image.Image:
    """
    S26 Ultra High-Definition Edge Refinement & De-Haloing Pipeline:
    1. Removes bottom display stands/holders and restores white blister card margins.
    2. Optional Full-Resolution RGB Guided Filter (for raw camera JPEGs).
    3. Shape-Faithful Subpixel Contour Anti-Aliasing (preserves boxes, blister cards, and bottles).
    4. Multi-Pass RGB Edge Color Decontamination so zero dark/grey background halo remains.
    """
    w, h = rgba_img.size
    m = mask_pil.resize((w, h), Image.Resampling.BICUBIC)

    try:
        import numpy as np

        if run_guided:
            guided_01 = _guided_filter_fullres(
                rgba_img.convert("RGB"),
                np.asarray(m, dtype=np.float32) / 255.0,
                radius=max(3, min(w, h) // 140),
                eps=8e-4,
            )
            m = Image.fromarray(np.clip(guided_01 * 255.0, 0, 255).astype(np.uint8), mode="L")

        m_np = np.asarray(m, dtype=np.uint8)
        m_np = _remove_bottom_display_stand(m_np)
        rgba_img, m_np = _restore_white_card_margins_and_hang_hole(rgba_img, m_np)
        m = Image.fromarray(m_np, mode="L")
    except Exception as e:
        logger.debug("Stand/card refinement fallback: %s", e)

    m = m.filter(ImageFilter.MedianFilter(size=3))
    m = _smooth_contour_non_destructive(m)
    m = m.filter(ImageFilter.GaussianBlur(radius=0.95))
    m = m.point(lambda a: 0 if a < 78 else (255 if a > 216 else int((a - 78) * 255 / 138)))

    try:
        import numpy as np

        rgb_orig = rgba_img.convert("RGB")
        rgb_int1 = rgb_orig.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
        rgb_int2 = rgb_int1.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
        orig_np = np.asarray(rgb_orig, dtype=np.float32)
        int1_np = np.asarray(rgb_int1, dtype=np.float32)
        int2_np = np.asarray(rgb_int2, dtype=np.float32)
        alpha_np = np.asarray(m, dtype=np.float32) / 255.0

        outer_rim = ((alpha_np > 0.01) & (alpha_np < 0.65))[:, :, np.newaxis]
        inner_rim = ((alpha_np >= 0.65) & (alpha_np < 0.95))[:, :, np.newaxis]
        clean_np = np.where(
            outer_rim,
            0.18 * orig_np + 0.82 * int2_np,
            np.where(inner_rim, 0.50 * orig_np + 0.50 * int1_np, orig_np),
        )
        out = Image.fromarray(np.clip(clean_np, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
        out.putalpha(m)
        return out
    except Exception:
        out = rgba_img.copy()
        out.putalpha(m)
        return out


def _reconstruct_white_product_if_hollow(rgba_img: Image.Image, mask_arr, run_guided: bool = True):
    """
    Handles overexposed white/bright cylindrical containers photographed against bright walls
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
    corner_clutter[: int(h * 0.34), int(w * 0.68) :] = True
    corner_clutter[: int(h * 0.34), : int(w * 0.32)] = True

    cx1, cx2 = int(w * 0.38), int(w * 0.62)
    cy1, cy2 = int(h * 0.20), int(h * 0.68)
    spine_gray = gray[cy1:cy2, cx1:cx2]
    spine_mask = mask_arr[cy1:cy2, cx1:cx2] > 110
    bright_ratio = float((spine_gray > 216).mean())
    mask_fill_ratio = float(spine_mask.mean())

    if bright_ratio > 0.68 and mask_fill_ratio < 0.45:
        mask_arr = np.where(corner_clutter, 0, mask_arr).astype(np.uint8)
        fg_bin = fg_bin & (~corner_clutter)

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

    refined = _refine_product_edges_and_dehalo(rgba_img, Image.fromarray(mask_arr, mode="L"), run_guided=run_guided)
    return refined, np.asarray(refined.getchannel("A"), dtype=np.uint8)


def _auto_straighten_tilted_product(rgba_img: Image.Image) -> Image.Image:
    """
    Automatically detects if a product was photographed at a slant/tilt (صور بمايل)
    and counter-rotates the RGBA cutout so the product stands 100% plumb and vertical.
    """
    try:
        import numpy as np

        w, h = rgba_img.size
        alpha = np.asarray(rgba_img.getchannel("A"), dtype=np.uint8)
        fg = alpha > 95
        ys = np.where(fg.any(axis=1))[0]
        if len(ys) < 40:
            return rgba_img

        y0, y1 = int(ys[0]), int(ys[-1])
        fh = y1 - y0 + 1
        if fh < 40:
            return rgba_img

        # Analyze the main torso (22%..78% of height) to measure vertical axis tilt
        s_idx = int(fh * 0.22)
        e_idx = int(fh * 0.78)
        if e_idx - s_idx < 16:
            return rgba_img

        row_y = []
        row_xl = []
        row_xr = []
        row_xm = []
        row_span = []
        for y in range(y0 + s_idx, y0 + e_idx):
            xs = np.where(fg[y])[0]
            if len(xs) >= 10:
                xl = float(xs[0])
                xr = float(xs[-1])
                row_y.append(float(y))
                row_xl.append(xl)
                row_xr.append(xr)
                row_xm.append(0.5 * (xl + xr))
                row_span.append(xr - xl)

        if len(row_y) < 16:
            return rgba_img

        ry = np.array(row_y, dtype=np.float32)
        rxl = np.array(row_xl, dtype=np.float32)
        rxr = np.array(row_xr, dtype=np.float32)
        rxm = np.array(row_xm, dtype=np.float32)
        rspan = np.array(row_span, dtype=np.float32)

        med_span = float(np.median(rspan))
        if med_span < 20:
            return rgba_img

        # Keep rows whose width is consistent with the main body so caps/shoulders don't skew slope
        inliers = np.abs(rspan - med_span) <= (med_span * 0.18)
        if int(inliers.sum()) < 12:
            inliers = np.ones_like(rspan, dtype=bool)

        y_in = ry[inliers]
        if float(y_in.max() - y_in.min()) < fh * 0.25:
            return rgba_img

        slope_mid = float(np.polyfit(y_in, rxm[inliers], 1)[0])
        slope_l = float(np.polyfit(y_in, rxl[inliers], 1)[0])
        slope_r = float(np.polyfit(y_in, rxr[inliers], 1)[0])

        # Left and right walls should tilt in the same direction (parallel walls tilted together)
        if abs(slope_l - slope_r) > 0.18 and (slope_l * slope_r) < 0:
            return rgba_img

        avg_slope = 0.50 * slope_mid + 0.25 * slope_l + 0.25 * slope_r
        angle_deg = float(np.degrees(np.arctan(avg_slope)))

        # Only auto-correct meaningful tilts between 1.1° and 28.0°
        if 1.1 <= abs(angle_deg) <= 28.0:
            # In image coords (y downward), dx/dy > 0 means bottom shifts right (counter-clockwise tilt),
            # while PIL Image.rotate(angle) rotates counter-clockwise for positive angles, so we rotate by -angle_deg.
            straightened = rgba_img.rotate(
                -angle_deg,
                resample=Image.Resampling.BICUBIC,
                expand=True,
                fillcolor=(0, 0, 0, 0),
            )
            return straightened
        return rgba_img
    except Exception as e:
        logger.debug("Auto-straighten skipped: %s", e)
        return rgba_img


def _apply_studio_relighting(prod_rgba: Image.Image, filter_mode: str = "auto_hdr") -> Image.Image:
    """
    Commercial Studio Softbox Relighting & Multi-Filter Engine (applied strictly to isolated product):
    Supports filter_mode:
    - 'auto_hdr': Balanced studio exposure lift, 3D softbox specular sheen, crisp micro-contrast.
    - 'vivid_pop': Rich flagship store colors, deep contrast, vibrant packaging pop.
    - 'crisp_white': Neutralizes warm/yellow indoor color casts and brightens white products.
    - 'warm_luxury': Subtle golden-hour luxury boutique warmth and smooth contrast.
    - 'sharp_detail': High-definition dual-band sharpening for fine text and electronics.
    - 'natural': True-to-life original color tone with light optical sharpening.
    """
    filter_mode = (filter_mode or "auto_hdr").strip().lower()
    r, g, b, a = prod_rgba.split()
    rgb_img = Image.merge("RGB", (r, g, b))

    if filter_mode == "natural":
        rgb_img = rgb_img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=95, threshold=2))
        r2, g2, b2 = rgb_img.split()
        return Image.merge("RGBA", (r2, g2, b2, a))

    try:
        import numpy as np

        rgb = np.asarray(rgb_img, dtype=np.float32)
        alpha_np = np.asarray(a, dtype=np.float32) / 255.0
        fg_mask = alpha_np > 0.5

        if fg_mask.sum() > 50:
            # Automatic gray-world / highlight white-balance correction for 'crisp_white' and 'auto_hdr'
            if filter_mode in ("crisp_white", "auto_hdr"):
                lum_pre = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
                bright_neutral = fg_mask & (lum_pre > np.percentile(lum_pre[fg_mask], 70))
                if bright_neutral.sum() > 30:
                    mr = float(np.median(rgb[:, :, 0][bright_neutral]))
                    mg = float(np.median(rgb[:, :, 1][bright_neutral]))
                    mb = float(np.median(rgb[:, :, 2][bright_neutral]))
                    m_avg = (mr + mg + mb) / 3.0
                    if m_avg > 80.0:
                        strength = 0.65 if filter_mode == "crisp_white" else 0.28
                        wb_r = 1.0 + strength * ((m_avg / max(mr, 1.0)) - 1.0)
                        wb_g = 1.0 + strength * ((m_avg / max(mg, 1.0)) - 1.0)
                        wb_b = 1.0 + strength * ((m_avg / max(mb, 1.0)) - 1.0)
                        rgb[:, :, 0] = np.clip(rgb[:, :, 0] * np.clip(wb_r, 0.88, 1.14), 0.0, 255.0)
                        rgb[:, :, 1] = np.clip(rgb[:, :, 1] * np.clip(wb_g, 0.90, 1.12), 0.0, 255.0)
                        rgb[:, :, 2] = np.clip(rgb[:, :, 2] * np.clip(wb_b, 0.88, 1.18), 0.0, 255.0)

            if filter_mode == "warm_luxury":
                rgb[:, :, 0] = np.clip(rgb[:, :, 0] * 1.045, 0.0, 255.0)
                rgb[:, :, 1] = np.clip(rgb[:, :, 1] * 1.015, 0.0, 255.0)
                rgb[:, :, 2] = np.clip(rgb[:, :, 2] * 0.955, 0.0, 255.0)

            lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
            fg_lum = lum[fg_mask]
            p50 = float(np.percentile(fg_lum, 50))
            p92 = float(np.percentile(fg_lum, 92))

            target_peak = 246.0 if filter_mode == "crisp_white" else 242.0
            gain = 1.0
            if p92 < 238.0 and p92 > 40.0:
                gain = min(1.26, target_peak / p92)
            gamma = 1.0
            if p50 * gain < 158.0:
                gamma = max(0.76, min(0.95, (p50 * gain) / 170.0))

            norm = np.clip((rgb * gain) / 255.0, 0.0, 1.0)
            if gamma < 0.99:
                norm = norm ** gamma

            contrast_k = 1.12 if filter_mode == "vivid_pop" else (1.09 if filter_mode == "sharp_detail" else 1.07)
            norm = np.clip(0.5 + (norm - 0.5) * contrast_k, 0.0, 1.0)

            h, w, _ = rgb.shape
            xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[np.newaxis, :, np.newaxis]
            sheen_amp = 0.055 if filter_mode in ("vivid_pop", "warm_luxury") else 0.045
            softbox_sheen = 1.0 + sheen_amp * np.exp(-((xs - 0.36) ** 2) / (2.0 * (0.18 ** 2)))
            norm = np.clip(norm * softbox_sheen, 0.0, 1.0)

            rgb_img = Image.fromarray((norm * 255.0).astype(np.uint8), mode="RGB")
    except Exception as e:
        logger.debug("Studio relighting fallback: %s", e)

    sat_factor = 1.24 if filter_mode == "vivid_pop" else (0.96 if filter_mode == "crisp_white" else 1.10)
    rgb_img = ImageEnhance.Color(rgb_img).enhance(sat_factor)

    if filter_mode == "sharp_detail":
        rgb_img = rgb_img.filter(ImageFilter.UnsharpMask(radius=1.8, percent=165, threshold=2))
    else:
        rgb_img = rgb_img.filter(ImageFilter.UnsharpMask(radius=1.6, percent=130, threshold=2))

    r2, g2, b2 = rgb_img.split()
    return Image.merge("RGBA", (r2, g2, b2, a))


def _remove_background_edge_aware_fallback(img: Image.Image) -> Image.Image:
    """Upgraded pure-Pillow edge-stopped, multi-seed border flood-fill with interior hole filling."""
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

    return _refine_product_edges_and_dehalo(rgba, mask_small, run_guided=True)


def _remove_background_smart(img: Image.Image) -> Image.Image:
    """Primary AI + Computer Vision studio background segmentation pipeline."""
    rgba = img.convert("RGBA")
    orig_w, orig_h = rgba.size

    sess, model_kind = _ensure_ai_runtime()
    if sess is not None:
        try:
            import numpy as np

            rgb = rgba.convert("RGB")
            pred1 = _run_ai_pass(sess, model_kind, rgb)

            boosted = ImageOps.autocontrast(rgb, cutoff=1)
            boosted = ImageEnhance.Contrast(boosted).enhance(1.30)
            boosted = boosted.filter(ImageFilter.UnsharpMask(radius=3, percent=160, threshold=2))
            pred2 = _run_ai_pass(sess, model_kind, boosted)

            ph, pw = pred1.shape
            yy, xx = np.mgrid[0:ph, 0:pw]
            dist_center = (((xx - pw * 0.50) / (pw * 0.50)) ** 2 + ((yy - ph * 0.48) / (ph * 0.50)) ** 2) ** 0.5
            center_prior = np.clip(1.12 - 0.40 * dist_center, 0.35, 1.05).astype(np.float32)

            combined = np.maximum(pred1, pred2 * 0.88) * center_prior
            c_min, c_max = float(combined.min()), float(combined.max())
            if c_max - c_min > 1e-6:
                combined = (combined - c_min) / (c_max - c_min)

            # Component cleanup on 320x320 grid for fast O(N) flood fill
            comb_320 = np.asarray(
                Image.fromarray(np.clip(combined * 255.0, 0, 255).astype(np.uint8), mode="L").resize(
                    (320, 320), Image.Resampling.BILINEAR
                ),
                dtype=np.float32,
            ) / 255.0
            cleaned_320 = _filter_central_components_and_fill_holes(comb_320)
            gate_full = (
                np.asarray(
                    Image.fromarray(np.clip(cleaned_320 * 255.0, 0, 255).astype(np.uint8), mode="L").resize(
                        (pw, ph), Image.Resampling.BICUBIC
                    ),
                    dtype=np.float32,
                )
                / 255.0
            )
            final_pred = np.where(gate_full > 0.15, np.maximum(combined, gate_full * 0.85), 0.0)

            mask_u8_small = Image.fromarray(np.clip(final_pred * 255.0, 0, 255).astype(np.uint8), mode="L")
            mask_full = mask_u8_small.resize((orig_w, orig_h), Image.Resampling.BICUBIC)
            mask_np = np.asarray(mask_full, dtype=np.uint8)

            out, _ = _reconstruct_white_product_if_hollow(rgba, mask_np, run_guided=True)
            return out
        except Exception as e:
            logger.warning("AI segmentation fallback triggered: %s", e)

    out_fb = _remove_background_edge_aware_fallback(rgba)
    try:
        import numpy as np

        mask_np = np.asarray(out_fb.getchannel("A"), dtype=np.uint8)
        out_fb, _ = _reconstruct_white_product_if_hollow(out_fb, mask_np, run_guided=True)
    except Exception:
        pass
    return out_fb


def _create_studio_stage(target_size: int, bg_style: str = "studio_white") -> Image.Image:
    """
    Creates a seamless, artifact-free 3D luxury boutique photography stage.
    Supports: 'studio_white', 'studio_dark', 'studio_gold', 'studio_marble'.
    """
    bg_style = (bg_style or "studio_white").strip().lower()
    try:
        import numpy as np

        yy, xx = np.mgrid[0:target_size, 0:target_size].astype(np.float32)
        nx = (xx - target_size * 0.50) / (target_size * 0.50)
        ny = (yy - target_size * 0.42) / (target_size * 0.50)
        rad = np.sqrt(nx ** 2 + ny ** 2)
        spot = np.clip(1.0 - (rad / 1.35) ** 1.6, 0.0, 1.0)

        floor_t = np.clip((yy / target_size - 0.68) / 0.32, 0.0, 1.0)
        horizon_dip = np.exp(-(((yy / target_size) - 0.74) ** 2) / (2.0 * (0.045 ** 2)))
        floor_sheen = np.exp(-(((yy / target_size) - 0.79) ** 2) / (2.0 * (0.07 ** 2))) * np.clip(1.0 - np.abs(nx) * 0.75, 0.0, 1.0)

        if bg_style == "studio_dark":
            r = 8.0 + 24.0 * spot - 4.0 * horizon_dip + 8.0 * (floor_t ** 1.4) + 10.0 * floor_sheen
            g = 13.0 + 36.0 * spot - 6.0 * horizon_dip + 12.0 * (floor_t ** 1.4) + 16.0 * floor_sheen
            b = 26.0 + 62.0 * spot - 8.0 * horizon_dip + 22.0 * (floor_t ** 1.4) + 28.0 * floor_sheen
        elif bg_style == "studio_gold":
            r = 240.0 + 15.0 * spot - 7.0 * horizon_dip - 4.0 * (floor_t ** 1.5) + 6.0 * floor_sheen
            g = 234.0 + 17.0 * spot - 8.0 * horizon_dip - 6.0 * (floor_t ** 1.5) + 5.0 * floor_sheen
            b = 220.0 + 16.0 * spot - 10.0 * horizon_dip - 9.0 * (floor_t ** 1.5) + 3.0 * floor_sheen
        elif bg_style == "studio_marble":
            vein = np.sin((xx * 0.015 + yy * 0.008) + np.sin(yy * 0.012) * 1.4) * 3.2
            r = 228.0 + 20.0 * spot - 7.0 * horizon_dip - 4.0 * (floor_t ** 1.4) + vein * 0.6 + 6.0 * floor_sheen
            g = 232.0 + 18.0 * spot - 6.0 * horizon_dip - 3.0 * (floor_t ** 1.4) + vein * 0.6 + 6.0 * floor_sheen
            b = 238.0 + 15.0 * spot - 5.0 * horizon_dip - 2.0 * (floor_t ** 1.4) + vein * 0.8 + 7.0 * floor_sheen
        else:
            r = 238.0 + 17.0 * spot - 6.0 * horizon_dip - 3.0 * (floor_t ** 1.5) + 4.0 * floor_sheen
            g = 242.0 + 13.0 * spot - 5.0 * horizon_dip - 2.0 * (floor_t ** 1.5) + 4.0 * floor_sheen
            b = 248.0 + 7.0 * spot - 3.0 * horizon_dip - 1.0 * (floor_t ** 1.5) + 3.0 * floor_sheen

        rgb = np.stack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255)], axis=-1).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB").convert("RGBA")
    except Exception:
        base_col = (10, 15, 28, 255) if bg_style == "studio_dark" else (246, 248, 252, 255)
        return Image.new("RGBA", (target_size, target_size), base_col)


def _paste_luxury_floor_reflection(canvas: Image.Image, prod_rgba: Image.Image, px: int, py: int, bg_style: str = "studio_white") -> Image.Image:
    """
    Renders a subtle polished-showroom mirror reflection directly beneath the product base.
    """
    try:
        import numpy as np

        cw, ch = canvas.size
        pw, ph = prod_rgba.size
        ref_h = max(18, min(int(ph * 0.24), ch - (py + ph) - 12))
        if ref_h < 18:
            return canvas

        flipped = ImageOps.flip(prod_rgba).crop((0, 0, pw, ref_h))
        blurred = flipped.filter(ImageFilter.GaussianBlur(radius=2.2))

        arr = np.asarray(blurred, dtype=np.float32)
        fade = np.linspace(1.0, 0.0, ref_h, dtype=np.float32)[:, np.newaxis] ** 1.9
        max_opacity = 0.17 if bg_style == "studio_dark" else 0.13
        arr[:, :, 3] = np.clip(arr[:, :, 3] * fade * max_opacity, 0.0, 255.0)
        ref_img = Image.fromarray(arr.astype(np.uint8), mode="RGBA")

        layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(ref_img, (px, py + ph - 2), ref_img)
        return Image.alpha_composite(canvas, layer)
    except Exception:
        return canvas


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
    """Applies the official Raqamiyat 3D die-cut crystal shield & 'كفالة رقميات' bottom hallmark."""
    # 1. Top-right 3D die-cut crystal shield emblem
    if os.path.exists(EMBLEM_PATH):
        try:
            emblem = Image.open(EMBLEM_PATH).convert("RGBA")
            emb_size = max(58, int(target_size * 0.112))
            emblem_resized = emblem.resize((emb_size, emb_size), Image.Resampling.LANCZOS)
            pad = int(target_size * 0.026)
            ex = target_size - emb_size - pad
            ey = pad
            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                emblem_resized.getchannel("A"),
                (ex, ey + 4),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.28 if bg_style == "studio_white" else 0.58,
                blur_radius=7,
            )
            canvas.paste(emblem_resized, (ex, ey), emblem_resized)
        except Exception as ee:
            logger.warning("Could not apply emblem: %s", ee)

    # 2. Bottom centered 'كفالة رقميات' official warranty badge
    if os.path.exists(MASTER_BADGE_PATH):
        try:
            badge = Image.open(MASTER_BADGE_PATH).convert("RGBA")
            target_bw = int(target_size * 0.48)
            target_bh = max(24, int(badge.height * (target_bw / badge.width)))
            badge_resized = badge.resize((target_bw, target_bh), Image.Resampling.LANCZOS)

            bx = (target_size - target_bw) // 2
            by = target_size - target_bh - int(target_size * 0.024)

            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                badge_resized.getchannel("A"),
                (bx, by + 4),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.30 if bg_style == "studio_white" else 0.62,
                blur_radius=9,
            )
            canvas.paste(badge_resized, (bx, by), badge_resized)
        except Exception as be:
            logger.warning("Could not apply hallmark badge: %s", be)

    return canvas


def _heal_transparent_rgb_fringe(rgba_img: Image.Image) -> Image.Image:
    """
    When Android ML Kit uploads a PNG cutout, pixels with alpha=0 have RGB=(0,0,0) black.
    This function fills transparent/semi-transparent pixels with dilated interior product colors
    so edge anti-aliasing never bleeds black.
    """
    try:
        import numpy as np

        arr = np.asarray(rgba_img, dtype=np.float32)
        rgb = arr[:, :, :3]
        a = arr[:, :, 3:4] / 255.0

        safe_a = np.maximum(a, 0.15)
        unpremult = np.where((a > 0.05) & (a < 0.95), np.clip(rgb / safe_a, 0.0, 255.0), rgb)
        rgb_pil = Image.fromarray(unpremult.astype(np.uint8), mode="RGB")

        dilated = rgb_pil.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MaxFilter(7))
        dil_np = np.asarray(dilated, dtype=np.float32)

        neutral_bg = np.full_like(rgb, 246.0)
        near_edge = (a <= 0.05) & (np.asarray(rgba_img.getchannel("A").filter(ImageFilter.MaxFilter(15))) > 10)[
            :, :, np.newaxis
        ]
        healed_rgb = np.where(a > 0.25, unpremult, np.where(near_edge, dil_np, neutral_bg))
        out = Image.fromarray(np.clip(healed_rgb, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
        out.putalpha(rgba_img.getchannel("A"))
        return out
    except Exception:
        return rgba_img


def process_camera_product_snapshot(
    image_file,
    isolate_white=True,
    add_hallmark=True,
    target_size=800,
    store_name=None,
    bg_style="studio_white",
    manual_rotate=0.0,
    crop_box=None,
    crop_polygon=None,
    auto_straighten=True,
    filter_mode="auto_hdr",
):
    """
    Transforms a raw mobile camera product photo into an ultra-luxury e-commerce studio shot.
    Supports manual freeform polygon crop, multi-direction bounding box crop, manual rotation,
    automatic tilt/slant correction, luxury showroom floor reflections, and studio filters.
    """
    try:
        if isinstance(image_file, Image.Image):
            img = image_file.copy()
        elif hasattr(image_file, "read"):
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

        max_dim = 1440
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # 1. Apply user rotation first (if requested) so crop coordinates align with what the user sees
        try:
            rot_deg = float(manual_rotate or 0.0)
        except (TypeError, ValueError):
            rot_deg = 0.0
        if abs(rot_deg) >= 0.2:
            # Negative angle so positive slider rotates clockwise intuitively in UI
            img = img.rotate(-rot_deg, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))

        # 2. Apply user freeform polygon selection (if provided) — overrides/guides AI around exact user boundary
        user_poly_applied = False
        if crop_polygon and isinstance(crop_polygon, (list, tuple)) and len(crop_polygon) >= 3:
            try:
                iw, ih = img.size
                pts = []
                for pt in crop_polygon:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        px_pt = max(0.0, min(float(iw), float(pt[0]) * iw))
                        py_pt = max(0.0, min(float(ih), float(pt[1]) * ih))
                        pts.append((px_pt, py_pt))
                if len(pts) >= 3:
                    poly_mask = Image.new("L", (iw, ih), 0)
                    ImageDraw.Draw(poly_mask).polygon(pts, fill=255)
                    poly_mask = poly_mask.filter(ImageFilter.GaussianBlur(radius=1.2))
                    orig_a = img.getchannel("A")
                    import numpy as np
                    combined_a = np.minimum(np.asarray(orig_a, dtype=np.uint8), np.asarray(poly_mask, dtype=np.uint8))
                    img.putalpha(Image.fromarray(combined_a, mode="L"))
                    pb = poly_mask.getbbox()
                    if pb and (pb[2] - pb[0]) > 20 and (pb[3] - pb[1]) > 20:
                        img = img.crop(pb)
                        user_poly_applied = True
            except Exception as poly_exc:
                logger.warning("Polygon crop skipped: %s", poly_exc)

        # 3. Apply user 8-handle / multi-direction rectangular crop box (if provided)
        if not user_poly_applied and crop_box and isinstance(crop_box, (list, tuple)) and len(crop_box) == 4:
            try:
                iw, ih = img.size
                x1 = max(0, min(iw - 1, int(float(crop_box[0]) * iw)))
                y1 = max(0, min(ih - 1, int(float(crop_box[1]) * ih)))
                x2 = max(x1 + 20, min(iw, int(float(crop_box[2]) * iw)))
                y2 = max(y1 + 20, min(ih, int(float(crop_box[3]) * ih)))
                if (x2 - x1) > 20 and (y2 - y1) > 20:
                    img = img.crop((x1, y1, x2, y2))
            except Exception as box_exc:
                logger.warning("Crop box skipped: %s", box_exc)

        if isolate_white:
            if user_poly_applied:
                # User manually drew the exact polygon cutout; heal edges without wiping user selection
                img = _heal_transparent_rgb_fringe(img)
            elif _has_meaningful_alpha(img):
                try:
                    import numpy as np

                    img = _heal_transparent_rgb_fringe(img)
                    alpha_np = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
                    alpha_320 = Image.fromarray(np.clip(alpha_np * 255.0, 0, 255).astype(np.uint8), mode="L").resize(
                        (320, 320), Image.Resampling.BILINEAR
                    )
                    cleaned_320 = _filter_central_components_and_fill_holes(
                        np.asarray(alpha_320, dtype=np.float32) / 255.0
                    )
                    gate_full_pil = Image.fromarray(
                        np.clip(cleaned_320 * 255.0, 0, 255).astype(np.uint8), mode="L"
                    ).resize(img.size, Image.Resampling.BICUBIC)
                    gate_full = np.asarray(gate_full_pil, dtype=np.float32) / 255.0

                    # Preserve 100% of full-resolution ML Kit foreground inside the central component gate
                    kept_full = np.where(gate_full > 0.15, np.maximum(alpha_np, gate_full * 0.90), 0.0)
                    img, _ = _reconstruct_white_product_if_hollow(
                        img,
                        np.clip(kept_full * 255.0, 0, 255).astype(np.uint8),
                        run_guided=False,
                    )
                except Exception as e:
                    logger.warning("Alpha refinement fallback: %s", e)
            else:
                img = _remove_background_smart(img)

            # 4. Automatic tilt/slant correction (تصحيح الميلان التلقائي) if enabled & user didn't rotate manually
            if auto_straighten and abs(rot_deg) < 0.2:
                img = _auto_straighten_tilted_product(img)

            alpha = img.getchannel("A")
            bbox = alpha.point(lambda a: 255 if a > 32 else 0).getbbox()
            if bbox:
                bw = bbox[2] - bbox[0]
                bh = bbox[3] - bbox[1]
                if bw > 20 and bh > 20:
                    img = img.crop(bbox)

            w, h = img.size
            canvas = _create_studio_stage(target_size, bg_style=bg_style)

            max_prod_w = int(target_size * 0.74)
            max_prod_h = int(target_size * 0.70)
            scale = min(max_prod_w / w, max_prod_h / h)
            nw = max(16, int(w * scale))
            nh = max(16, int(h * scale))
            resized_prod = img.resize((nw, nh), Image.Resampling.LANCZOS)

            resized_prod = _apply_studio_relighting(resized_prod, filter_mode=filter_mode)
            prod_alpha = resized_prod.getchannel("A")

            px = (target_size - nw) // 2
            py = int(target_size * 0.435) - (nh // 2)
            py = max(int(target_size * 0.045), py)

            # 1. Luxury Showroom Floor Mirror Reflection
            canvas = _paste_luxury_floor_reflection(canvas, resized_prod, px, py, bg_style=bg_style)

            # 2. Soft 360-degree 3D Silhouette Ambient Drop Shadow
            canvas = _paste_soft_shadow_from_alpha(
                canvas,
                prod_alpha,
                (px, py + 6),
                shadow_rgb=(15, 23, 42),
                opacity_scale=0.16 if bg_style != "studio_dark" else 0.42,
                blur_radius=max(12, target_size // 48),
            )

            # 3. Grounding Studio Floor Contact Shadow directly under product base
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

            # 4. Composite isolated & relit product
            canvas.paste(resized_prod, (px, py), resized_prod)
        else:
            img = _apply_studio_relighting(img, filter_mode=filter_mode)
            w, h = img.size
            min_side = min(w, h)
            crop_x = (w - min_side) // 2
            crop_y = (h - min_side) // 2
            square_img = img.crop((crop_x, crop_y, crop_x + min_side, crop_y + min_side))
            canvas = square_img.resize((target_size, target_size), Image.Resampling.LANCZOS)

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
