import os
import logging
from django.conf import settings
from django.templatetags.static import static

logger = logging.getLogger(__name__)

BRAND_STATIC_SVG_MAP = {
    # Games
    'pubg': 'site/img/brands/pubg.svg',
    'ببجي': 'site/img/brands/pubg.svg',
    'free fire': 'site/img/brands/freefire.svg',
    'freefire': 'site/img/brands/freefire.svg',
    'فايتر': 'site/img/brands/freefire.svg',
    'فري فاير': 'site/img/brands/freefire.svg',
    'roblox': 'site/img/brands/roblox.svg',
    'roblex': 'site/img/brands/roblox.svg',
    'روبلوكس': 'site/img/brands/roblox.svg',
    'jawaker': 'site/img/brands/jawaker.svg',
    'جواكر': 'site/img/brands/jawaker.svg',
    'yalla ludo': 'site/img/brands/yallaludo.svg',
    'yallaludo': 'site/img/brands/yallaludo.svg',
    'يلا لودو': 'site/img/brands/yallaludo.svg',
    'لودو': 'site/img/brands/yallaludo.svg',
    'brawl stars': 'site/img/brands/brawlstars.svg',
    'brawlstars': 'site/img/brands/brawlstars.svg',
    'براول ستارز': 'site/img/brands/brawlstars.svg',
    'hay day': 'site/img/brands/hayday.svg',
    'hayday': 'site/img/brands/hayday.svg',
    'هاي داي': 'site/img/brands/hayday.svg',
    'clash of clans': 'site/img/brands/clashofclans.svg',
    'clash royale': 'site/img/brands/clashofclans.svg',
    'clash': 'site/img/brands/clashofclans.svg',
    'كلاش': 'site/img/brands/clashofclans.svg',
    'mobile legends': 'site/img/brands/mobilelegends.svg',
    'mobilelegends': 'site/img/brands/mobilelegends.svg',
    'موبايل ليجند': 'site/img/brands/mobilelegends.svg',
    'valorant': 'site/img/brands/valorant.svg',
    'فالورانت': 'site/img/brands/valorant.svg',
    'فالورنت': 'site/img/brands/valorant.svg',
    'call of duty': 'site/img/brands/cod.svg',
    'cod': 'site/img/brands/cod.svg',
    'كود': 'site/img/brands/cod.svg',
    'كول أوف ديوتي': 'site/img/brands/cod.svg',
    'ea fc': 'site/img/brands/cod.svg',
    'fifa': 'site/img/brands/cod.svg',
    'فيفا': 'site/img/brands/cod.svg',
    
    # Gaming & Consoles
    'razer': 'site/img/brands/razer.svg',
    'رازر': 'site/img/brands/razer.svg',
    'ريزر': 'site/img/brands/razer.svg',
    'steam': 'site/img/brands/steam.svg',
    'ستيم': 'site/img/brands/steam.svg',
    'playstation': 'site/img/brands/playstation.svg',
    'بلايستيشن': 'site/img/brands/playstation.svg',
    'psn': 'site/img/brands/playstation.svg',
    'سوني': 'site/img/brands/playstation.svg',
    'xbox': 'site/img/brands/xbox.svg',
    'اكس بوكس': 'site/img/brands/xbox.svg',
    'إكس بوكس': 'site/img/brands/xbox.svg',
    
    # App Stores & Tech Brands
    'google play': 'site/img/brands/googleplay.svg',
    'google': 'site/img/brands/googleplay.svg',
    'جوجل بلاي': 'site/img/brands/googleplay.svg',
    'قوقل بلاي': 'site/img/brands/googleplay.svg',
    'itunes': 'site/img/brands/apple.svg',
    'apple': 'site/img/brands/apple.svg',
    'ابل': 'site/img/brands/apple.svg',
    'آبل': 'site/img/brands/apple.svg',
    'ايتونز': 'site/img/brands/apple.svg',

    # Streaming & Music
    'netflix': 'site/img/brands/netflix.svg',
    'نتفلكس': 'site/img/brands/netflix.svg',
    'نتفليكس': 'site/img/brands/netflix.svg',
    'shahid': 'site/img/brands/shahid.svg',
    'شاهد': 'site/img/brands/shahid.svg',
    'osn': 'site/img/brands/osn.svg',
    'او اس ان': 'site/img/brands/osn.svg',
    'disney': 'site/img/brands/osn.svg',
    'ديزني': 'site/img/brands/osn.svg',
    'spotify': 'site/img/brands/spotify.svg',
    'سبوتيفاي': 'site/img/brands/spotify.svg',
    'سبوتفاي': 'site/img/brands/spotify.svg',
    'anghami': 'site/img/brands/anghami.svg',
    'انغامي': 'site/img/brands/anghami.svg',
    'أنغامي': 'site/img/brands/anghami.svg',
    'youtube': 'site/img/brands/youtube.svg',
    'يوتيوب': 'site/img/brands/youtube.svg',

    # Social & Chat
    'facebook': 'site/img/brands/facebook.svg',
    'فيسبوك': 'site/img/brands/facebook.svg',
    'فيس بوك': 'site/img/brands/facebook.svg',
    'فيس': 'site/img/brands/facebook.svg',
    'whatsapp': 'site/img/brands/whatsapp.svg',
    'واتساب': 'site/img/brands/whatsapp.svg',
    'واتس اب': 'site/img/brands/whatsapp.svg',
    'واتس': 'site/img/brands/whatsapp.svg',
    'instagram': 'site/img/brands/instagram.svg',
    'انستغرام': 'site/img/brands/instagram.svg',
    'انستقرام': 'site/img/brands/instagram.svg',
    'انستا': 'site/img/brands/instagram.svg',
    'flaticon': 'site/img/brands/flaticon.svg',
    'فلاتيكون': 'site/img/brands/flaticon.svg',
    'tiktok': 'site/img/brands/tiktok.svg',
    'tik tok': 'site/img/brands/tiktok.svg',
    'تيك توك': 'site/img/brands/tiktok.svg',
    'تيكتوك': 'site/img/brands/tiktok.svg',
    'telegram': 'site/img/brands/telegram.svg',
    'تيليجرام': 'site/img/brands/telegram.svg',
    'تليجرام': 'site/img/brands/telegram.svg',
    'تلغرام': 'site/img/brands/telegram.svg',
    'discord': 'site/img/brands/discord.svg',
    'دسكورد': 'site/img/brands/discord.svg',
    'ديسكورد': 'site/img/brands/discord.svg',
    'snapchat': 'site/img/brands/snapchat.svg',
    'snap': 'site/img/brands/snapchat.svg',
    'سناب شات': 'site/img/brands/snapchat.svg',
    'سناب': 'site/img/brands/snapchat.svg',
    'bigo': 'site/img/brands/bigo.svg',
    'بيجو': 'site/img/brands/bigo.svg',
    'بيغو': 'site/img/brands/bigo.svg',
    'likee': 'site/img/brands/likee.svg',
    'لايكي': 'site/img/brands/likee.svg',

    # AI & Productivity
    'chatgpt': 'site/img/brands/chatgpt.svg',
    'openai': 'site/img/brands/chatgpt.svg',
    'gpt': 'site/img/brands/chatgpt.svg',
    'شات جي بي تي': 'site/img/brands/chatgpt.svg',
    'ذكاء اصطناعي': 'site/img/brands/chatgpt.svg',
    'canva': 'site/img/brands/canva.svg',
    'كانفا': 'site/img/brands/canva.svg',

    # VPN & Security
    'vpn': 'site/img/brands/vpn.svg',
    'بروكسي': 'site/img/brands/vpn.svg',
    'nordvpn': 'site/img/brands/vpn.svg',
    'expressvpn': 'site/img/brands/vpn.svg',
    'kaspersky': 'site/img/brands/vpn.svg',
    'adguard': 'site/img/brands/vpn.svg',
    'browsec': 'site/img/brands/vpn.svg',

    # Telecom / Networks
    'asiacell': 'site/img/brands/zain.svg',
    'آسيا سيل': 'site/img/brands/zain.svg',
    'اسياسيل': 'site/img/brands/zain.svg',
    'korek': 'site/img/brands/turkcell.svg',
    'كورك': 'site/img/brands/turkcell.svg',
    'syriatel': 'site/img/brands/syriatel.svg',
    'سيريتل': 'site/img/brands/syriatel.svg',
    'سيرياتيل': 'site/img/brands/syriatel.svg',
    'mtn': 'site/img/brands/mtn.svg',
    'ام تي ان': 'site/img/brands/mtn.svg',
    'stc': 'site/img/brands/stc.svg',
    'سوا': 'site/img/brands/stc.svg',
    'اس تي سي': 'site/img/brands/stc.svg',
    'zain': 'site/img/brands/zain.svg',
    'زين': 'site/img/brands/zain.svg',
    'turkcell': 'site/img/brands/turkcell.svg',
    'توركسيل': 'site/img/brands/turkcell.svg',
    'تروكسل': 'site/img/brands/turkcell.svg',
    'vodafone': 'site/img/brands/vodafone.svg',
    'فودافون': 'site/img/brands/vodafone.svg',
    'telekom': 'site/img/brands/turkcell.svg',
    'تليكوم': 'site/img/brands/turkcell.svg',

    # Social & App Stores
    'twitter': 'site/img/brands/facebook.svg',
    'تويتر': 'site/img/brands/facebook.svg',
    'x': 'site/img/brands/facebook.svg',
    'gemini': 'site/img/brands/chatgpt.svg',
    'جيميناي': 'site/img/brands/chatgpt.svg',
    'meyo': 'site/img/brands/bigo.svg',
    'ميو': 'site/img/brands/bigo.svg',
    'livu': 'site/img/brands/bigo.svg',
    'لايف يو': 'site/img/brands/bigo.svg',
    'mixu': 'site/img/brands/bigo.svg',
    'ميكس يو': 'site/img/brands/bigo.svg',
    'tumile': 'site/img/brands/bigo.svg',
    'توميل': 'site/img/brands/bigo.svg',
    'zepeto': 'site/img/brands/yallaludo.svg',
    'zepito': 'site/img/brands/yallaludo.svg',
    'زيبيتو': 'site/img/brands/yallaludo.svg',
    'azar': 'site/img/brands/bigo.svg',
    'أزار': 'site/img/brands/bigo.svg',
    'tango': 'site/img/brands/bigo.svg',
    'تانجو': 'site/img/brands/bigo.svg',
    'imo': 'site/img/brands/whatsapp.svg',
    'إيمو': 'site/img/brands/whatsapp.svg',
    'party star': 'site/img/brands/yallaludo.svg',
    'بارتي ستار': 'site/img/brands/yallaludo.svg',
    'blue 4k': 'site/img/brands/osn.svg',
    'بلو 4k': 'site/img/brands/osn.svg',
    'look tv': 'site/img/brands/osn.svg',
    'لوك تي في': 'site/img/brands/osn.svg',
    'barakat tv': 'site/img/brands/osn.svg',
    'بركات تي في': 'site/img/brands/osn.svg',
    'shamana tv': 'site/img/brands/osn.svg',
    'شامنا تي في': 'site/img/brands/osn.svg',
    'iptv': 'site/img/brands/osn.svg',
    'آي بي تي في': 'site/img/brands/osn.svg',
}

DEFAULT_FALLBACK_SVG = 'site/img/brands/generic_digital.svg'

def match_brand_static_asset(text):
    if not text:
        return None
    t = text.lower()
    for brand, path in BRAND_STATIC_SVG_MAP.items():
        if brand in t:
            return static(path)
    return None

def _extract_url_from_field(val):
    if not val:
        return None
    try:
        if isinstance(val, str):
            val_s = val.strip()
            if val_s.startswith(('http://', 'https://', '/')):
                if 'wikimedia.org' not in val_s and 'seeklogo.com' not in val_s:
                    return val_s
        elif hasattr(val, 'url') and val.url:
            val_s = str(val.url).strip()
            if 'wikimedia.org' not in val_s and 'seeklogo.com' not in val_s:
                return val_s
    except Exception:
        pass
    return None

def get_product_image_url(product, depth=0, allow_db=True):
    """
    Multi-tier intelligent image resolution for catalog products:
    1. Direct product media: image, thumbnail, cover_image.
    2. High-resolution brand static SVG matching (0ms in-memory).
    3. Product metadata image URLs (Alkasr/Tafa3ol/SMM API fields).
    4. Category image / brand matching.
    5. (If allow_db) Check gallery, linked ProviderProduct, or parent product.
    6. High-end Raqamiyat brand luxury SVG fallback.
    """
    if not product:
        return static(DEFAULT_FALLBACK_SVG)

    # 1. Direct product media fields
    for attr in ('image', 'thumbnail', 'cover_image'):
        val = getattr(product, attr, None)
        u = _extract_url_from_field(val)
        if u:
            return u

    # 2. High-resolution brand static SVG matching by product name (instant in-memory)
    p_name = getattr(product, 'name', '')
    brand_asset = match_brand_static_asset(p_name)
    if brand_asset:
        return brand_asset

    # 3. Product metadata (image_url, icon_url, artworkUrl512, etc.)
    try:
        meta = getattr(product, 'metadata', None)
        if isinstance(meta, dict):
            for k in ('image_url', 'image', 'icon_url', 'icon', 'artworkUrl512', 'artworkUrl100', 'logo_url', 'logo'):
                v = meta.get(k)
                u = _extract_url_from_field(v)
                if u:
                    return u
    except Exception:
        pass

    # 4. Category image & category brand matching
    cat = getattr(product, 'category', None)
    if cat:
        u = _extract_url_from_field(getattr(cat, 'image', None))
        if u:
            return u
        cat_name = getattr(cat, 'name', '')
        cat_asset = match_brand_static_asset(cat_name)
        if cat_asset:
            return cat_asset

    # 5. Database fallbacks (only if allow_db is True)
    if allow_db:
        # Check gallery images
        try:
            gallery_mgr = getattr(product, 'gallery', None)
            if gallery_mgr:
                first_gal = gallery_mgr.first()
                if first_gal:
                    u = _extract_url_from_field(getattr(first_gal, 'image', None)) or _extract_url_from_field(getattr(first_gal, 'url', None))
                    if u:
                        return u
        except Exception:
            pass

        # Linked ProviderProduct image via provider mappings
        try:
            if hasattr(product, 'provider_mappings'):
                first_m = product.provider_mappings.select_related('provider_product').first()
                if first_m and first_m.provider_product:
                    pp = first_m.provider_product
                    u = _extract_url_from_field(getattr(pp, 'local_image', None))
                    if u:
                        return u
        except Exception:
            pass

        # If this is a tenant sub-store product, check the global platform parent product
        if depth == 0 and getattr(product, 'store_id', None):
            try:
                from apps.catalog.models import Product
                parent = Product.all_objects.filter(store__isnull=True, name=product.name).first()
                if parent and parent.id != product.id:
                    parent_img = get_product_image_url(parent, depth=depth + 1, allow_db=False)
                    if parent_img and not parent_img.endswith(DEFAULT_FALLBACK_SVG):
                        return parent_img
            except Exception:
                pass

    # 6. Fallback to official Raqamiyat high-tech luxury brand emblem
    return static(DEFAULT_FALLBACK_SVG)


