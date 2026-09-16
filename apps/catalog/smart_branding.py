import os
import io
import re
import math
import logging
import urllib.parse
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from django.core.files.base import ContentFile
from django.utils.text import slugify

logger = logging.getLogger(__name__)



KNOWN_SEARCH_TERMS = {
    "facebook": "Facebook",
    "فيسبوك": "Facebook",
    "فيس": "Facebook",
    "fb": "Facebook",
    "whatsapp": "WhatsApp",
    "واتساب": "WhatsApp",
    "واتس": "WhatsApp",
    "instagram": "Instagram",
    "انستغرام": "Instagram",
    "انستقرام": "Instagram",
    "انستا": "Instagram",
    "twitter": "X",
    "تويتر": "X",
    "flaticon": "Flaticon",
    "فلاتيكون": "Flaticon",
    "freepik": "Freepik",
    "فري بيك": "Freepik",
    "envato": "Envato",
    "adobe": "Adobe",
    "ادوبي": "Adobe",
    "photoshop": "Adobe Photoshop",
    "فوتوشوب": "Adobe Photoshop",
    "illustrator": "Adobe Illustrator",
    "windows": "Microsoft Windows",
    "ويندوز": "Microsoft Windows",
    "office": "Microsoft 365",
    "اوفيس": "Microsoft 365",
    "kaspersky": "Kaspersky",
    "كاسبر": "Kaspersky",
    "midjourney": "Midjourney",
    "pubg": "PUBG MOBILE",
    "ببجي": "PUBG MOBILE",
    "free fire": "Free Fire",
    "فري فاير": "Free Fire",
    "roblox": "Roblox",
    "روبلوكس": "Roblox",
    "tiktok": "TikTok",
    "تيك توك": "TikTok",
    "netflix": "Netflix",
    "نتفلكس": "Netflix",
    "shahid": "Shahid",
    "شاهد": "Shahid",
    "jawaker": "Jawaker",
    "جواكر": "Jawaker",
    "yalla ludo": "Yalla Ludo",
    "يلا لودو": "Yalla Ludo",
    "clash of clans": "Clash of Clans",
    "كلاش أوف كلانس": "Clash of Clans",
    "كلاش رويال": "Clash Royale",
    "clash royale": "Clash Royale",
    "mobile legends": "Mobile Legends",
    "موبايل ليجند": "Mobile Legends",
    "weplay": "WePlay",
    "وي بلاي": "WePlay",
    "bigo": "Bigo Live",
    "بيجو": "Bigo Live",
    "likee": "Likee",
    "لايكي": "Likee",
    "toptop": "TopTop",
    "توب توب": "TopTop",
    "snapchat": "Snapchat",
    "سناب شات": "Snapchat",
    "telegram": "Telegram",
    "تليجرام": "Telegram",
    "تلغرام": "Telegram",
    "discord": "Discord",
    "دسكورد": "Discord",
    "spotify": "Spotify",
    "سبوتيفاي": "Spotify",
    "youtube": "YouTube",
    "يوتيوب": "YouTube",
    "chatgpt": "ChatGPT",
    "canva": "Canva",
    "كانفا": "Canva",
    "picsart": "Picsart",
    "بيكس آرت": "Picsart",
    "syriatel": "Syriatel",
    "سيريتل": "Syriatel",
    "mtn": "MTN",
    "ام تي ان": "MTN",
    "turkcell": "Turkcell",
    "تروكسل": "Turkcell",
    "vodafone": "Vodafone",
    "فودافون": "Vodafone",
    "telekom": "Turk Telekom",
    "تليكوم": "Turk Telekom",
    "disney": "Disney+",
    "ديزني": "Disney+",
    "osn": "OSN+",
    "او اس ان": "OSN+",
    "cyberghost": "CyberGhost VPN",
    "cyber ghost": "CyberGhost VPN",
    "browsec": "Browsec VPN",
    "ipvanish": "IPVanish VPN",
    "pia": "Private Internet Access",
    "planet vpn": "Planet VPN",
    "openvpn": "OpenVPN",
    "adguard": "AdGuard",
}

KNOWN_DOMAINS = {
    "facebook": "facebook.com",
    "فيسبوك": "facebook.com",
    "فيس": "facebook.com",
    "whatsapp": "whatsapp.com",
    "واتساب": "whatsapp.com",
    "واتس": "whatsapp.com",
    "instagram": "instagram.com",
    "انستغرام": "instagram.com",
    "انستا": "instagram.com",
    "flaticon": "flaticon.com",
    "فلاتيكون": "flaticon.com",
    "freepik": "freepik.com",
    "adobe": "adobe.com",
    "ادوبي": "adobe.com",
    "photoshop": "adobe.com",
    "windows": "microsoft.com",
    "ويندوز": "microsoft.com",
    "office": "office.com",
    "اوفيس": "office.com",
    "cyberghost": "cyberghostvpn.com",
    "cyber ghost": "cyberghostvpn.com",
    "browsec": "browsec.com",
    "ipvanish": "ipvanish.com",
    "pia": "privateinternetaccess.com",
    "planet vpn": "freevpnplanet.com",
    "openvpn": "openvpn.net",
    "adguard": "adguard.com",
    "kaspersky": "kaspersky.com",
    "كاسبر": "kaspersky.com",
    "midjourney": "midjourney.com",
    "tradingview": "tradingview.com",
    "duolingo": "duolingo.com",
}


def extract_search_query(product_name):
    """
    Intelligently extracts the best English or search keyword from a product name.
    """
    p_lower = (product_name or "").lower()

    # 1. Match known keywords dictionary
    for k, term in KNOWN_SEARCH_TERMS.items():
        if k in p_lower:
            return term

    # 2. Extract content inside parentheses if English characters exist
    m = re.search(r'\(([^)]+)\)', product_name or "")
    if m:
        inside = m.group(1).strip()
        inside_clean = re.sub(r'\b(global|tr|usa|ksa|uae|services|service|plus|vip|pro)\b', '', inside, flags=re.IGNORECASE).strip()
        if re.search(r'[a-zA-Z]{3,}', inside_clean):
            return inside_clean

    # 3. Extract English words if present
    eng_matches = re.findall(r'[a-zA-Z0-9\+]+', product_name or "")
    if eng_matches:
        filtered = [w for w in eng_matches if w.lower() not in ("global", "tr", "id", "vip", "pro", "coins", "diamonds", "uc")]
        if filtered:
            return " ".join(filtered[:3])

    # 4. Clean Arabic name
    clean_ar = re.sub(r'[\(\)\[\]\d\+\$]+', ' ', product_name or "").strip()
    return clean_ar or product_name


def fetch_image_from_itunes(query):
    """
    Searches Apple App Store API for the query and downloads the official 512x512 app icon.
    """
    if not query:
        return None
    try:
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit=1"
        resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                res = data["results"][0]
                img_url = res.get("artworkUrl512") or res.get("artworkUrl100")
                if img_url:
                    img_url = img_url.replace("100x100bb", "512x512bb")
                    img_resp = requests.get(img_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
                    if img_resp.status_code == 200:
                        return Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    except Exception as e:
        logger.debug("iTunes search error for query '%s': %s", query, e)
def fetch_image_from_domain(product_name):
    """
    Fetches high-resolution 256x256 official brand icons via Google High-Res Favicon API.
    """
    p_lower = (product_name or "").lower()
    for key, domain in KNOWN_DOMAINS.items():
        if key in p_lower:
            try:
                url = f"https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://{domain}&size=256"
                resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and len(resp.content) > 500:
                    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    if img.width >= 48 and img.height >= 48:
                        return img
            except Exception as e:
                logger.debug("Domain logo fetch error for '%s': %s", domain, e)
    return None


def search_and_download_logo(product_name):
    """
    Multi-source official logo search:
    1. Google High-Res Brand Domain API (Known Domains)
    2. iTunes App Store Official Icon Search (query)
    3. iTunes App Store Official Icon Search (broad keyword)
    """
    # 1. Known Domain Brand Logo
    img = fetch_image_from_domain(product_name)
    if img:
        return img

    query = extract_search_query(product_name)

    # 2. iTunes App Store API
    img = fetch_image_from_itunes(query)
    if img:
        return img

    # Try broader query if specific query failed
    if " " in query:
        first_word = query.split()[0]
        img = fetch_image_from_itunes(first_word)
        if img:
            return img

    return None


def draw_raqamiyat_verified_badge(card, width=600, height=600, store_name=None):
    """
    Draws the official luxury Raqamiyat Verified watermark badge:
    2x Supersampled anti-aliased glass capsule with glowing cyber shield,
    dual-layer official lightning bolt (cyan + white highlight),
    crisp connected Arabic brandmark, and verified emerald checkmark.
    """
    scale = 2
    target_w, target_h = 320, 60
    bw, bh = target_w * scale, target_h * scale

    badge = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)

    # 1. Ambient cyan glow
    glow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.rounded_rectangle([6, 6, bw - 6, bh - 6], radius=36, fill=(6, 182, 212, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    badge.paste(glow, (0, 0), glow)

    # 2. Luxury Glass capsule background
    draw.rounded_rectangle(
        [4, 4, bw - 4, bh - 4],
        radius=34,
        fill=(10, 16, 32, 248),
        outline=(6, 182, 212, 210),
        width=3
    )

    # 3. Inner top specular rim
    draw.line([(40, 6), (bw - 40, 6)], fill=(255, 255, 255, 75), width=2)

    # 4. Hexagonal Cyber Shield for Raqamiyat Icon
    sx, sy = 24, 18
    sw, sh = 84, 84
    shield_pts = [
        (sx + sw // 2, sy),
        (sx + sw, sy + sh // 4),
        (sx + sw, sy + sh * 3 // 4),
        (sx + sw // 2, sy + sh),
        (sx, sy + sh * 3 // 4),
        (sx, sy + sh // 4)
    ]
    draw.polygon(shield_pts, fill=(14, 25, 52, 255), outline=(34, 211, 238, 240), width=3)

    # 5. Official Raqamiyat Twin-Layer Lightning Bolt (Cyan Outer + Pure White Specular Core)
    bolt_outer = [
        (sx + sw // 2 + 8, sy + 10),
        (sx + 18, sy + 44),
        (sx + sw // 2 - 2, sy + 44),
        (sx + sw // 2 - 10, sy + sh - 10),
        (sx + sw - 16, sy + 38),
        (sx + sw // 2 + 4, sy + 38)
    ]
    draw.polygon(bolt_outer, fill=(6, 182, 212, 255))

    bolt_inner = [
        (sx + sw // 2 + 6, sy + 18),
        (sx + 26, sy + 42),
        (sx + sw // 2 - 2, sy + 42),
        (sx + sw // 2 - 7, sy + sh - 22),
        (sx + sw - 24, sy + 40),
        (sx + sw // 2 + 3, sy + 40)
    ]
    draw.polygon(bolt_inner, fill=(255, 255, 255, 250))

    # 6. Typography
    font_ar = None
    for font_name in ("segoeuib.ttf", "tahoma.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            font_ar = ImageFont.truetype(f"C:/Windows/Fonts/{font_name}", 38)
            break
        except Exception:
            pass
    if not font_ar:
        try:
            font_ar = ImageFont.truetype("arialbd.ttf", 38)
        except Exception:
            font_ar = ImageFont.load_default()

    font_en = None
    for font_name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            font_en = ImageFont.truetype(f"C:/Windows/Fonts/{font_name}", 20)
            break
        except Exception:
            pass
    if not font_en:
        try:
            font_en = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font_en = ImageFont.load_default()

    # Connected Arabic Brandmark ('رقميات' in Presentation Forms)
    ar_text = "\uFE95\uFE8E\uFEF4\uFEE4\uFED7\uFEAD"
    draw.text((128, 14), ar_text, fill=(255, 255, 255, 255), font=font_ar)

    # Subtitle / Store name
    en_text = "RAQAMIYAT \u2022 VERIFIED" if not store_name else f"{str(store_name).upper()[:16]} \u2022 STORE"
    draw.text((130, 68), en_text, fill=(34, 211, 238, 240), font=font_en)

    # 7. Emerald Verified Badge
    vx, vy, vr = bw - 60, bh // 2, 22
    draw.ellipse([vx - vr, vy - vr, vx + vr, vy + vr], fill=(16, 185, 129, 255), outline=(255, 255, 255, 60), width=2)
    draw.line([(vx - 10, vy), (vx - 2, vy + 8), (vx + 11, vy - 8)], fill=(255, 255, 255, 255), width=5)

    # Downscale with Lanczos for razor-sharp anti-aliasing
    final_badge = badge.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Paste onto card
    badge_x = (width - target_w) // 2
    badge_y = height - target_h - 22
    if isinstance(card, Image.Image):
        card.paste(final_badge, (badge_x, badge_y), final_badge)


def compose_branded_card(logo_img, product_name, store_name=None, width=600, height=600):
    """
    Composes a studio-quality 600x600px square card:
    - Dark tech background with smooth cyan radial glow
    - Rounded card boundary with subtle 1px border
    - Centered official logo inside a soft glass container with realistic drop shadow
    - Official Raqamiyat Verified watermark badge
    Returns None if no real logo_img is provided (prevents generic dummy icon generation).
    """
    if not logo_img:
        return None

    card = Image.new("RGBA", (width, height), (8, 12, 22, 255))
    draw = ImageDraw.Draw(card)

    # 1. Background radial glow
    cx, cy = width // 2, (height // 2) - 20
    for r in range(260, 20, -10):
        alpha = int(28 * (1 - r / 260))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(6, 182, 212, alpha))

    # 2. Outer rounded border
    draw.rounded_rectangle(
        [12, 12, width - 12, height - 12],
        radius=36,
        outline=(255, 255, 255, 25),
        width=1
    )

    # 3. Luxury App Icon Container
    box_size = 320
    bx = (width - box_size) // 2
    by = (height - box_size) // 2 - 15

    # Realistic drop shadow behind container
    shadow_size = box_size + 40
    shadow = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([20, 20, box_size + 20, box_size + 20], radius=64, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    card.paste(shadow, (bx - 20, by - 15), shadow)

    # Glass container box
    container = Image.new("RGBA", (box_size, box_size), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(container)
    c_draw.rounded_rectangle([0, 0, box_size, box_size], radius=64, fill=(15, 23, 42, 245), outline=(255, 255, 255, 35), width=2)

    # Centered Logo inside container
    icon_size = 220
    logo_copy = logo_img.copy().convert("RGBA")
    logo_copy.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
    icon_x = (box_size - logo_copy.width) // 2
    icon_y = (box_size - logo_copy.height) // 2
    container.paste(logo_copy, (icon_x, icon_y), logo_copy)

    card.paste(container, (bx, by), container)

    # 4. Draw Official Raqamiyat Luxury Watermark Badge
    draw_raqamiyat_verified_badge(card, width, height, store_name)

    return card.convert("RGB")


def apply_branding_to_product(product, force=False):
    """
    Main function to brand a single product:
    Searches the internet for the official logo, composes the branded card with Raqamiyat badge,
    and updates product.image.
    If no real logo is found and force=True, clears any old dummy generated image so that
    the product falls back cleanly to static brand SVGs or category assets.
    """
    if product.image and not force:
        return False

    store_name = product.store.name if product.store else None

    # Search internet for real official app/service logo
    logo_img = search_and_download_logo(product.name)

    if not logo_img:
        # If forcing update and no logo could be found,
        # clear any previously saved dummy card image so the system falls back cleanly to static brand SVGs
        if force and product.image:
            try:
                product.image.delete(save=False)
            except Exception:
                pass
            product.image = None
            product.save(update_fields=['image'])
        return False

    card_img = compose_branded_card(
        logo_img=logo_img,
        product_name=product.name,
        store_name=store_name
    )
    if not card_img:
        return False

    buf = io.BytesIO()
    card_img.save(buf, format="JPEG", quality=93)
    filename = f"{slugify(product.name) or 'product'}_{str(product.id)[:8]}.jpg"

    product.image.save(filename, ContentFile(buf.getvalue()), save=True)
    return True
