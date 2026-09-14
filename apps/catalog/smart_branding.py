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

# Direct High-Resolution Fallback Logos for Top Games, Brands & Services
CURATED_FALLBACK_LOGOS = {
    "steam": "https://cdn.iconscout.com/icon/free/png-512/free-steam-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461794.png?f=webp&w=512",
    "playstation": "https://cdn.iconscout.com/icon/free/png-512/free-playstation-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461789.png?f=webp&w=512",
    "razer": "https://cdn.iconscout.com/icon/free/png-512/free-razer-logo-icon-download-in-svg-png-gif-file-formats--logos-brands-pack-icons-3442938.png?f=webp&w=512",
    "xbox": "https://cdn.iconscout.com/icon/free/png-512/free-xbox-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461807.png?f=webp&w=512",
    "google play": "https://cdn.iconscout.com/icon/free/png-512/free-google-play-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461782.png?f=webp&w=512",
    "apple": "https://cdn.iconscout.com/icon/free/png-512/free-apple-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461769.png?f=webp&w=512",
    "itunes": "https://cdn.iconscout.com/icon/free/png-512/free-apple-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461769.png?f=webp&w=512",
}

KNOWN_SEARCH_TERMS = {
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
}


def extract_search_query(product_name):
    """
    Intelligently extracts the best English or search keyword from a product name.
    Examples:
    'ببجي موبايل (PUBG Global)' -> 'PUBG MOBILE'
    'تيك توك (TikTok)' -> 'TikTok'
    'فري فاير (Free Fire)' -> 'Free Fire'
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
    return None


def fetch_image_from_curated(query, product_name):
    """
    Checks direct curated fallback URLs for top brands.
    """
    combined = f"{query} {product_name}".lower()
    for key, cdn_url in CURATED_FALLBACK_LOGOS.items():
        if key in combined:
            try:
                resp = requests.get(cdn_url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    return Image.open(io.BytesIO(resp.content)).convert("RGBA")
            except Exception as e:
                logger.debug("Curated logo fetch error for '%s': %s", key, e)
    return None


def search_and_download_logo(product_name):
    """
    Primary internet search pipeline:
    1. iTunes App Store Official Icon Search (highest quality, transparent 512x512 PNGs)
    2. Curated High-Definition CDN Library
    """
    query = extract_search_query(product_name)
    
    # 1. iTunes App Store API
    img = fetch_image_from_itunes(query)
    if img:
        return img

    # Try broader query if specific query failed
    if " " in query:
        first_word = query.split()[0]
        img = fetch_image_from_itunes(first_word)
        if img:
            return img

    # 2. Curated CDN Library
    img = fetch_image_from_curated(query, product_name)
    if img:
        return img

    return None


def draw_raqamiyat_verified_badge(draw, width=600, height=600, store_name=None):
    """
    Draws the official Raqamiyat Verified watermark badge:
    Glassmorphic pill at bottom center with glowing cyan bolt and crisp typography.
    """
    badge_w = 230
    badge_h = 46
    bx = (width - badge_w) // 2
    by = height - badge_h - 26

    # Glass container background
    draw.rounded_rectangle(
        [bx, by, bx + badge_w, by + badge_h],
        radius=14,
        fill=(10, 16, 30, 240),
        outline=(6, 182, 212, 190),
        width=1
    )

    # Official Raqamiyat Lightning Bolt Emblem (Vector Polygon)
    bolt = [
        (bx + 26, by + 11),
        (bx + 14, by + 25),
        (bx + 23, by + 25),
        (bx + 20, by + 35),
        (bx + 32, by + 20),
        (bx + 24, by + 20)
    ]
    draw.polygon(bolt, fill=(6, 182, 212, 255))

    # Crisp Latin Typography
    text = "RAQAMIYAT VERIFIED" if not store_name else f"{store_name.upper()} STORE"[:20]
    try:
        font = ImageFont.truetype("arialbd.ttf", 15)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 15)
        except Exception:
            font = ImageFont.load_default()

    draw.text((bx + 40, by + 14), text, fill=(255, 255, 255, 245), font=font)


def compose_branded_card(logo_img, product_name, store_name=None, width=600, height=600):
    """
    Composes a studio-quality 600x600px square card:
    - Dark tech background with smooth cyan radial glow
    - Rounded card boundary with subtle 1px border
    - Centered official logo with rounded corners and realistic drop shadow
    - Official Raqamiyat Verified watermark badge
    """
    card = Image.new("RGBA", (width, height), (8, 12, 22, 255))
    draw = ImageDraw.Draw(card)

    # 1. Background radial glow
    cx, cy = width // 2, (height // 2) - 15
    for r in range(250, 20, -10):
        alpha = int(24 * (1 - r / 250))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(6, 182, 212, alpha))

    # 2. Outer rounded border
    draw.rounded_rectangle(
        [12, 12, width - 12, height - 12],
        radius=36,
        outline=(255, 255, 255, 25),
        width=1
    )

    if logo_img:
        # Resize logo to 340x340
        logo_size = 340
        logo_copy = logo_img.copy().convert("RGBA")
        logo_copy = logo_copy.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

        # Smooth rounded corners on logo
        mask = Image.new("L", (logo_size, logo_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, logo_size, logo_size], radius=68, fill=255)

        # Realistic drop shadow behind the logo
        shadow_size = logo_size + 40
        shadow = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rounded_rectangle([15, 15, logo_size + 25, logo_size + 25], radius=68, fill=(0, 0, 0, 180))
        shadow = shadow.filter(ImageFilter.GaussianBlur(16))

        pos_x = (width - logo_size) // 2
        pos_y = (height - logo_size) // 2 - 12

        card.paste(shadow, (pos_x - 20, pos_y - 15), shadow)
        card.paste(logo_copy, (pos_x, pos_y), mask)
    else:
        # Clean geometric tech fallback if no internet logo was found
        draw.ellipse([cx - 100, cy - 100, cx + 100, cy + 100], fill=(15, 23, 42, 255), outline=(6, 182, 212, 200), width=2)
        bolt = [
            (cx + 10, cy - 50),
            (cx - 30, cy + 5),
            (cx - 2, cy + 5),
            (cx - 15, cy + 50),
            (cx + 30, cy - 10),
            (cx + 5, cy - 10)
        ]
        draw.polygon(bolt, fill=(6, 182, 212, 255))

    # 3. Draw Raqamiyat Watermark Badge
    draw_raqamiyat_verified_badge(draw, width, height, store_name)

    return card.convert("RGB")


def apply_branding_to_product(product, force=False):
    """
    Main function to brand a single product:
    Searches the internet for the official logo, composes the branded card with Raqamiyat badge,
    and updates product.image.
    """
    if product.image and not force:
        return False

    store_name = product.store.name if product.store else None

    # Search internet for real official app/service logo
    logo_img = search_and_download_logo(product.name)

    card_img = compose_branded_card(
        logo_img=logo_img,
        product_name=product.name,
        store_name=store_name
    )

    buf = io.BytesIO()
    card_img.save(buf, format="JPEG", quality=93)
    filename = f"{slugify(product.name) or 'product'}_{str(product.id)[:8]}.jpg"

    product.image.save(filename, ContentFile(buf.getvalue()), save=True)
    return True
