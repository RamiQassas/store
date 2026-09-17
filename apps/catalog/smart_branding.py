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

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = lambda t: t

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
MASTER_BADGE_PATH = os.path.join(ASSETS_DIR, "raqamiyat_master_badge.png")
EMBLEM_PATH = os.path.join(ASSETS_DIR, "raqamiyat_emblem.png")

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
    "steam": "Steam Mobile",
    "ستيم": "Steam Mobile",
    "playstation": "PlayStation App",
    "بلايستيشن": "PlayStation App",
    "psn": "PlayStation App",
    "سوني": "PlayStation App",
    "xbox": "Xbox",
    "اكس بوكس": "Xbox",
    "razer": "Razer Cortex",
    "رازر": "Razer Cortex",
    "brawl stars": "Brawl Stars",
    "براول ستارز": "Brawl Stars",
    "hay day": "Hay Day",
    "هاي داي": "Hay Day",
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
    "steam": "steampowered.com",
    "ستيم": "steampowered.com",
    "playstation": "playstation.com",
    "بلايستيشن": "playstation.com",
    "xbox": "xbox.com",
    "اكس بوكس": "xbox.com",
    "spotify": "spotify.com",
    "سبوتيفاي": "spotify.com",
    "netflix": "netflix.com",
    "نتفلكس": "netflix.com",
    "discord": "discord.com",
    "دسكورد": "discord.com",
    "roblox": "roblox.com",
    "روبلوكس": "roblox.com",
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


def create_squircle_mask(size, radius):
    """
    Creates an ultra-smooth antialiased squircle mask (Apple iOS curvature).
    Uses 4x supersampling for razor-sharp, perfectly curved edges.
    """
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [0, 0, size * scale - 1, size * scale - 1],
        radius=radius * scale,
        fill=255
    )
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def compose_branded_card(logo_img, product_name, store_name=None, width=600, height=600):
    """
    Composes an ultra-professional studio product card (600x600px):
    - Deep luxury dark studio canvas (#0b0f19) matching Raqamiyat store theme
    - Subtle ambient radial backlight centered behind the icon for depth
    - Official product icon presented as a floating Apple iOS squircle with soft 3D ambient drop shadow
    - Crisp subtle glass highlight rim around the squircle
    - Handles transparent logos (e.g. Steam, PlayStation, Discord) with a luxury frosted glass tile
    - NO ugly watermarks, badges, or text stamps - pure, ultra-clean, high-end icon presentation.
    """
    if not logo_img:
        return None

    card = Image.new("RGBA", (width, height), (9, 13, 22, 255))
    draw = ImageDraw.Draw(card)

    # 1. Outer subtle border
    draw.rounded_rectangle(
        [8, 8, width - 8, height - 8],
        radius=30,
        outline=(255, 255, 255, 14),
        width=1
    )

    # 2. Icon sizing & processing
    icon_size = 440
    ix = (width - icon_size) // 2
    iy = (height - icon_size) // 2
    corner_radius = int(icon_size * 0.22)

    # Detect transparency
    is_transparent = False
    if logo_img.mode in ("RGBA", "LA"):
        alpha_channel = logo_img.split()[-1]
        w_l, h_l = logo_img.size
        # Sample corners and edge points
        sample_points = [
            (0, 0), (w_l - 1, 0), (0, h_l - 1), (w_l - 1, h_l - 1),
            (w_l // 2, 2), (2, h_l // 2)
        ]
        if any(alpha_channel.getpixel(pt) < 220 for pt in sample_points):
            is_transparent = True

    # 4. Realistic 3D floating drop shadow
    shadow_margin = 35
    shadow_size = icon_size + shadow_margin * 2
    shadow = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [shadow_margin, shadow_margin + 12, shadow_margin + icon_size, shadow_margin + icon_size + 12],
        radius=corner_radius,
        fill=(0, 0, 0, 190)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    card.paste(shadow, (ix - shadow_margin, iy - shadow_margin), shadow)

    if is_transparent:
        # Luxury glass pill / tile container for transparent logos
        tile = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(tile)
        t_draw.rounded_rectangle(
            [0, 0, icon_size, icon_size],
            radius=corner_radius,
            fill=(18, 24, 38, 240),
            outline=(255, 255, 255, 30),
            width=2
        )
        # Resize logo to fit inside with elegant breathing room
        logo_fit = logo_img.copy().convert("RGBA")
        inner_pad = int(icon_size * 0.68)
        logo_fit.thumbnail((inner_pad, inner_pad), Image.Resampling.LANCZOS)
        lx = (icon_size - logo_fit.width) // 2
        ly = (icon_size - logo_fit.height) // 2
        tile.paste(logo_fit, (lx, ly), logo_fit)
        card.paste(tile, (ix, iy), tile)
    else:
        # Full squircle masked app icon with smooth rounded corners
        logo_resized = logo_img.copy().convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        mask = create_squircle_mask(icon_size, corner_radius)

        squircle_box = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
        squircle_box.paste(logo_resized, (0, 0), mask)

        # Subtle specular glass border around squircle
        b_draw = ImageDraw.Draw(squircle_box)
        b_draw.rounded_rectangle(
            [0, 0, icon_size - 1, icon_size - 1],
            radius=corner_radius,
            outline=(255, 255, 255, 40),
            width=2
        )

        card.paste(squircle_box, (ix, iy), squircle_box)

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
