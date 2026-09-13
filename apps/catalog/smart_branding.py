import os
import io
import math
import logging
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from django.core.files.base import ContentFile
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Curated High-Definition Official Vector / WebP / PNG Logo URLs for Famous Apps & Games
KNOWN_APP_LOGOS = {
    "tiktok": {
        "title": "TikTok",
        "bg_color": (1, 1, 1),
        "accent": (0, 242, 234),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-tiktok-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461805.png?f=webp&w=512"
    },
    "pubg": {
        "title": "PUBG Mobile",
        "bg_color": (15, 23, 42),
        "accent": (245, 158, 11),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-pubg-mobile-icon-download-in-svg-png-gif-file-formats--logo-games-pack-logos-icons-2630504.png?f=webp&w=512"
    },
    "free fire": {
        "title": "Free Fire",
        "bg_color": (20, 10, 5),
        "accent": (239, 68, 68),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-garena-free-fire-logo-icon-download-in-svg-png-gif-file-formats--battlegrounds-mobile-games-pack-logos-icons-3312891.png?f=webp&w=512"
    },
    "roblox": {
        "title": "Roblox",
        "bg_color": (15, 23, 42),
        "accent": (220, 38, 38),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-roblox-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461793.png?f=webp&w=512"
    },
    "netflix": {
        "title": "Netflix",
        "bg_color": (10, 10, 10),
        "accent": (229, 9, 20),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-netflix-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461787.png?f=webp&w=512"
    },
    "shahid": {
        "title": "Shahid VIP",
        "bg_color": (5, 15, 30),
        "accent": (14, 165, 233),
        "png_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Shahid_2022.svg/512px-Shahid_2022.svg.png"
    },
    "jawaker": {
        "title": "Jawaker",
        "bg_color": (26, 12, 10),
        "accent": (220, 38, 38),
        "png_url": ""
    },
    "mobile legends": {
        "title": "Mobile Legends",
        "bg_color": (10, 20, 40),
        "accent": (59, 130, 246),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-mobile-legends-logo-icon-download-in-svg-png-gif-file-formats--bang-game-android-apps-pack-logos-icons-3312892.png?f=webp&w=512"
    },
    "clash of clans": {
        "title": "Clash of Clans",
        "bg_color": (25, 20, 10),
        "accent": (245, 158, 11),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-clash-of-clans-logo-icon-download-in-svg-png-gif-file-formats--strategy-game-supercell-pack-logos-icons-3312889.png?f=webp&w=512"
    },
    "clash royale": {
        "title": "Clash Royale",
        "bg_color": (10, 20, 35),
        "accent": (59, 130, 246),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-clash-royale-logo-icon-download-in-svg-png-gif-file-formats--game-supercell-pack-logos-icons-3312890.png?f=webp&w=512"
    },
    "yalla ludo": {
        "title": "Yalla Ludo",
        "bg_color": (30, 15, 10),
        "accent": (239, 68, 68),
        "png_url": ""
    },
    "bigo": {
        "title": "Bigo Live",
        "bg_color": (5, 25, 30),
        "accent": (6, 182, 212),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-bigo-live-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-3312888.png?f=webp&w=512"
    },
    "likee": {
        "title": "Likee",
        "bg_color": (30, 5, 20),
        "accent": (236, 72, 153),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-likee-logo-icon-download-in-svg-png-gif-file-formats--social-media-video-pack-logos-icons-3312893.png?f=webp&w=512"
    },
    "steam": {
        "title": "Steam",
        "bg_color": (15, 23, 42),
        "accent": (59, 130, 246),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-steam-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461794.png?f=webp&w=512"
    },
    "playstation": {
        "title": "PlayStation",
        "bg_color": (5, 15, 35),
        "accent": (37, 99, 235),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-playstation-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461789.png?f=webp&w=512"
    },
    "itunes": {
        "title": "Apple iTunes",
        "bg_color": (10, 10, 15),
        "accent": (168, 85, 247),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-apple-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461769.png?f=webp&w=512"
    },
    "google play": {
        "title": "Google Play",
        "bg_color": (15, 23, 42),
        "accent": (16, 185, 129),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-google-play-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461782.png?f=webp&w=512"
    },
    "discord": {
        "title": "Discord Nitro",
        "bg_color": (15, 18, 35),
        "accent": (99, 102, 241),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-discord-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461775.png?f=webp&w=512"
    },
    "telegram": {
        "title": "Telegram Premium",
        "bg_color": (10, 25, 40),
        "accent": (14, 165, 233),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-telegram-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461798.png?f=webp&w=512"
    },
    "youtube": {
        "title": "YouTube Premium",
        "bg_color": (20, 5, 5),
        "accent": (239, 68, 68),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-youtube-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461808.png?f=webp&w=512"
    },
    "spotify": {
        "title": "Spotify",
        "bg_color": (5, 20, 10),
        "accent": (34, 197, 94),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-spotify-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461795.png?f=webp&w=512"
    },
    "snapchat": {
        "title": "Snapchat Plus",
        "bg_color": (25, 25, 5),
        "accent": (234, 179, 8),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-snapchat-logo-icon-download-in-svg-png-gif-file-formats--social-media-pack-logos-icons-461796.png?f=webp&w=512"
    },
    "chatgpt": {
        "title": "ChatGPT Plus",
        "bg_color": (10, 25, 25),
        "accent": (20, 184, 166),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-chatgpt-logo-icon-download-in-svg-png-gif-file-formats--artificial-intelligence-ai-openai-pack-logos-icons-7731782.png?f=webp&w=512"
    },
    "canva": {
        "title": "Canva Pro",
        "bg_color": (5, 20, 30),
        "accent": (6, 182, 212),
        "png_url": "https://cdn.iconscout.com/icon/free/png-512/free-canva-logo-icon-download-in-svg-png-gif-file-formats--technology-social-media-company-brand-vol-2-pack-logos-icons-3029962.png?f=webp&w=512"
    },
    "syriatel": {
        "title": "سيريتل Syriatel",
        "bg_color": (30, 10, 10),
        "accent": (239, 68, 68),
        "png_url": ""
    },
    "mtn": {
        "title": "ام تي ان MTN",
        "bg_color": (30, 25, 5),
        "accent": (234, 179, 8),
        "png_url": ""
    }
}


def find_app_preset(name, category=""):
    combined = f"{name or ''} {category or ''}".lower()
    
    for key in (
        "tiktok", "pubg", "free fire", "roblox", "netflix", "shahid",
        "jawaker", "mobile legends", "clash of clans", "clash royale",
        "yalla ludo", "bigo", "likee", "steam", "playstation", "itunes",
        "google play", "discord", "telegram", "youtube", "spotify",
        "snapchat", "chatgpt", "canva", "syriatel", "mtn"
    ):
        if key in combined:
            return key, KNOWN_APP_LOGOS[key]
        
    # Arabic matches
    if any(k in combined for k in ("تيك توك", "تيكتوك")):
        return "tiktok", KNOWN_APP_LOGOS["tiktok"]
    if any(k in combined for k in ("ببجي", "شدات")):
        return "pubg", KNOWN_APP_LOGOS["pubg"]
    if any(k in combined for k in ("فري فاير", "جواهر فري")):
        return "free fire", KNOWN_APP_LOGOS["free fire"]
    if any(k in combined for k in ("روبلوكس", "روبوكس")):
        return "roblox", KNOWN_APP_LOGOS["roblox"]
    if any(k in combined for k in ("نتفلكس", "نتفليكس")):
        return "netflix", KNOWN_APP_LOGOS["netflix"]
    if any(k in combined for k in ("شاهد", "شاهد vip")):
        return "shahid", KNOWN_APP_LOGOS["shahid"]
    if any(k in combined for k in ("جواكر", "توكنز جواكر")):
        return "jawaker", KNOWN_APP_LOGOS["jawaker"]
    if any(k in combined for k in ("يلا لودو", "لودو")):
        return "yalla ludo", KNOWN_APP_LOGOS["yalla ludo"]
    if any(k in combined for k in ("بيجو", "بيغو")):
        return "bigo", KNOWN_APP_LOGOS["bigo"]
    if any(k in combined for k in ("لايكي",)):
        return "likee", KNOWN_APP_LOGOS["likee"]
    if any(k in combined for k in ("سيريتل", "سيريتيل")):
        return "syriatel", KNOWN_APP_LOGOS["syriatel"]
    if any(k in combined for k in ("ام تي ان", "امتيان")):
        return "mtn", KNOWN_APP_LOGOS["mtn"]
    if any(k in combined for k in ("بلايستيشن", "بلاي ستيشن", "psn")):
        return "playstation", KNOWN_APP_LOGOS["playstation"]
    if any(k in combined for k in ("آيتونز", "ايتونز", "ابل")):
        return "itunes", KNOWN_APP_LOGOS["itunes"]
    if any(k in combined for k in ("جوجل بلاي", "قوقل بلاي")):
        return "google play", KNOWN_APP_LOGOS["google play"]
    if any(k in combined for k in ("ستيم",)):
        return "steam", KNOWN_APP_LOGOS["steam"]

    return None, None


def _draw_raqamiyat_badge(draw, width=600, height=600, store_name=None):
    """
    Renders an elegant glassmorphism badge with the Raqamiyat Bolt icon
    at the bottom of the card.
    """
    badge_w = 260
    badge_h = 44
    badge_x = (width - badge_w) // 2
    badge_y = height - badge_h - 28

    # Glass container background
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=14,
        fill=(15, 23, 42, 220),
        outline=(6, 182, 212, 160),
        width=1
    )

    # Glowing Bolt Icon
    bolt_pts = [
        (badge_x + 24, badge_y + 10),
        (badge_x + 14, badge_y + 24),
        (badge_x + 22, badge_y + 24),
        (badge_x + 19, badge_y + 34),
        (badge_x + 30, badge_y + 20),
        (badge_x + 23, badge_y + 20),
    ]
    draw.polygon(bolt_pts, fill=(6, 182, 212, 255))

    # Badge text
    label = f"رقميات | RAQAMIYAT" if not store_name else f"{store_name} | معتمد"
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        font = ImageFont.load_default()

    draw.text((badge_x + 38, badge_y + 12), label, fill=(248, 250, 252, 240), font=font)


def _draw_pro_placeholder_icon(draw, title, accent_color, width=600, height=600):
    """
    Draws a modern geometric 3D stylized emblem when an external PNG is not available.
    """
    cx, cy = width // 2, (height // 2) - 20
    radius = 110

    # Concentric glowing rings
    for r in range(radius + 40, radius - 10, -5):
        alpha = int(30 * (1 - (r - radius + 10) / 50))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent_color, max(alpha, 0)), width=2)

    # Core circle badge
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(15, 23, 42, 255), outline=accent_color, width=3)

    # Stylized Title Initial / Monogram
    initial = (title or "R")[:2].upper()
    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except Exception:
        font = ImageFont.load_default()

    draw.text((cx - 30, cy - 40), initial, fill=(255, 255, 255, 255), font=font)


def create_branded_product_image(product_name, category_name="", store_name=None, custom_logo_image=None):
    """
    Generates a high-quality 600x600px square card with dark radial gradient,
    centered crisp application logo, and integrated Raqamiyat verification badge.
    """
    width, height = 600, 600
    
    # 1. Base Image Canvas
    card = Image.new("RGBA", (width, height), (7, 11, 23, 255))
    draw = ImageDraw.Draw(card)

    app_key, preset = find_app_preset(product_name, category_name)
    accent = preset.get("accent", (6, 182, 212)) if preset else (6, 182, 212)

    # 2. Radial Glow in Background
    glow_center_x, glow_center_y = width // 2, (height // 2) - 20
    for r in range(260, 20, -8):
        alpha = int(28 * (1 - r / 260))
        draw.ellipse(
            [glow_center_x - r, glow_center_y - r, glow_center_x + r, glow_center_y + r],
            fill=(*accent, alpha)
        )

    # 3. Outer Rounded Border
    draw.rounded_rectangle(
        [16, 16, width - 16, height - 16],
        radius=40,
        outline=(*accent, 90),
        width=2
    )

    # 4. Fetch / Render the App Logo
    logo_placed = False
    logo_img = custom_logo_image

    if not logo_img and preset and preset.get("png_url"):
        try:
            resp = requests.get(preset["png_url"], timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                logo_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        except Exception as ex:
            logger.debug(f"Could not download logo for {app_key}: {ex}")

    if logo_img:
        try:
            # Resize while preserving aspect ratio
            max_size = 260
            logo_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            lw, lh = logo_img.size
            pos_x = (width - lw) // 2
            pos_y = (height - lh) // 2 - 25
            
            # Subtle drop shadow behind logo
            shadow = Image.new("RGBA", (lw + 20, lh + 20), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            s_draw.ellipse([10, 10, lw + 10, lh + 10], fill=(0, 0, 0, 140))
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            card.paste(shadow, (pos_x - 10, pos_y - 10), shadow)

            # Paste logo
            card.paste(logo_img, (pos_x, pos_y), logo_img)
            logo_placed = True
        except Exception as e:
            logger.warning(f"Error pasting logo: {e}")

    if not logo_placed:
        title = preset["title"] if preset else product_name
        _draw_pro_placeholder_icon(draw, title, accent, width, height)

    # 5. Draw Raqamiyat Watermark / Verification Badge
    _draw_raqamiyat_badge(draw, width, height, store_name)

    # 6. Return as RGB
    return card.convert("RGB")


def apply_branding_to_product(product, force=False):
    """
    Applies the automated branded image with Raqamiyat badge to a specific product.
    """
    if product.image and not force:
        return False

    cat_name = product.category.name if product.category else ""
    store_name = product.store.name if product.store else None

    img = create_branded_product_image(
        product_name=product.name,
        category_name=cat_name,
        store_name=store_name
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    filename = f"{slugify(product.name) or 'product'}_{str(product.id)[:8]}.jpg"

    product.image.save(filename, ContentFile(buf.getvalue()), save=True)
    return True
