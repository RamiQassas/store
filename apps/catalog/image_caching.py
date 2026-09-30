import os
import logging
from django.conf import settings
from django.templatetags.static import static

logger = logging.getLogger(__name__)

import re

BRAND_STATIC_SVG_MAP = {
    # Games
    'pubg mobile': 'site/img/brands/pubg.svg',
    'pubg turkey': 'site/img/brands/pubg.svg',
    'pubg global': 'site/img/brands/pubg.svg',
    'pupg mobile': 'site/img/brands/pubg.svg',
    'pupg': 'site/img/brands/pubg.svg',
    'pubg': 'site/img/brands/pubg.svg',
    'ببجي موبايل': 'site/img/brands/pubg.svg',
    'ببجي تركيا': 'site/img/brands/pubg.svg',
    'ببجي': 'site/img/brands/pubg.svg',
    'free fire': 'site/img/brands/freefire.svg',
    'freefire': 'site/img/brands/freefire.svg',
    'فري فاير': 'site/img/brands/freefire.svg',
    'roblox cards': 'site/img/brands/roblox.svg',
    'roblox card': 'site/img/brands/roblox.svg',
    'roblox': 'site/img/brands/roblox.svg',
    'roblex cards': 'site/img/brands/roblox.svg',
    'roblex': 'site/img/brands/roblox.svg',
    'بطاقات روبلوكس': 'site/img/brands/roblox.svg',
    'كروت روبلوكس': 'site/img/brands/roblox.svg',
    'روبلوكس': 'site/img/brands/roblox.svg',
    'روبلكس': 'site/img/brands/roblox.svg',
    'jawaker': 'site/img/brands/jawaker.svg',
    'جواكر': 'site/img/brands/jawaker.svg',
    'yalla ludo': 'site/img/brands/yallaludo.svg',
    'yallaludo': 'site/img/brands/yallaludo.svg',
    'يلا لودو': 'site/img/brands/yallaludo.svg',
    'brawl stars': 'site/img/brands/brawlstars.svg',
    'brawlstars': 'site/img/brands/brawlstars.svg',
    'براول ستارز': 'site/img/brands/brawlstars.svg',
    'hay day': 'site/img/brands/hayday.svg',
    'hayday': 'site/img/brands/hayday.svg',
    'هاي داي': 'site/img/brands/hayday.svg',
    'clash of clans': 'site/img/brands/clashofclans.svg',
    'clash royale': 'site/img/brands/clashofclans.svg',
    'كلاش أوف كلانس': 'site/img/brands/clashofclans.svg',
    'كلاش اوف كلانس': 'site/img/brands/clashofclans.svg',
    'كلاش رويال': 'site/img/brands/clashofclans.svg',
    'mobile legends': 'site/img/brands/mobilelegends.svg',
    'mobilelegends': 'site/img/brands/mobilelegends.svg',
    'موبايل ليجندز': 'site/img/brands/mobilelegends.svg',
    'موبايل ليجند': 'site/img/brands/mobilelegends.svg',
    'valorant': 'site/img/brands/valorant.svg',
    'فالورانت': 'site/img/brands/valorant.svg',
    'call of duty mobile': 'site/img/brands/cod.svg',
    'call of duty': 'site/img/brands/cod.svg',
    'cod mobile': 'site/img/brands/cod.svg',
    'كول أوف ديوتي': 'site/img/brands/cod.svg',
    'كول اوف ديوتي': 'site/img/brands/cod.svg',
    'ea sports fc': 'site/img/brands/eafc.svg',
    'ea sports': 'site/img/brands/eafc.svg',
    'ea fc': 'site/img/brands/eafc.svg',
    'fifa mobile': 'site/img/brands/eafc.svg',
    'fifa': 'site/img/brands/eafc.svg',
    'فيفا': 'site/img/brands/eafc.svg',
    'honor of kings': 'site/img/brands/honorofkings.svg',
    'أونور أوف كينغز': 'site/img/brands/honorofkings.svg',
    'league of legends': 'site/img/brands/lol.svg',
    'lol rp': 'site/img/brands/lol.svg',
    'ليغ أوف ليجيندز': 'site/img/brands/lol.svg',

    # Gaming & Consoles & Gift Cards
    'razer gold': 'site/img/brands/razer.svg',
    'razer': 'site/img/brands/razer.svg',
    'ريزر جولد': 'site/img/brands/razer.svg',
    'ريزر': 'site/img/brands/razer.svg',
    'steam wallet': 'site/img/brands/steam.svg',
    'steam': 'site/img/brands/steam.svg',
    'ستيم': 'site/img/brands/steam.svg',
    'playstation store': 'site/img/brands/playstation.svg',
    'playstation network': 'site/img/brands/playstation.svg',
    'playstation': 'site/img/brands/playstation.svg',
    'بلايستيشن': 'site/img/brands/playstation.svg',
    'بلاي ستيشن': 'site/img/brands/playstation.svg',
    'xbox': 'site/img/brands/xbox.svg',
    'اكس بوكس': 'site/img/brands/xbox.svg',
    'إكس بوكس': 'site/img/brands/xbox.svg',
    'google play': 'site/img/brands/googleplay.svg',
    'جوجل بلاي': 'site/img/brands/googleplay.svg',
    'قوقل بلاي': 'site/img/brands/googleplay.svg',
    'apple itunes': 'site/img/brands/apple.svg',
    'itunes': 'site/img/brands/apple.svg',
    'apple': 'site/img/brands/apple.svg',
    'ايتونز': 'site/img/brands/apple.svg',
    'آيتونز': 'site/img/brands/apple.svg',
    'ابل': 'site/img/brands/apple.svg',
    'آبل': 'site/img/brands/apple.svg',
    'visa': 'site/img/brands/visa.svg',
    'فيزا': 'site/img/brands/visa.svg',

    # Streaming & TV
    'netflix': 'site/img/brands/netflix.svg',
    'نتفلكس': 'site/img/brands/netflix.svg',
    'نتفليكس': 'site/img/brands/netflix.svg',
    'shahid vip': 'site/img/brands/shahid.svg',
    'shahid': 'site/img/brands/shahid.svg',
    'شاهد vip': 'site/img/brands/shahid.svg',
    'شاهد': 'site/img/brands/shahid.svg',
    'osn': 'site/img/brands/osn.svg',
    'او اس ان': 'site/img/brands/osn.svg',
    'spotify': 'site/img/brands/spotify.svg',
    'سبوتيفاي': 'site/img/brands/spotify.svg',
    'anghami': 'site/img/brands/anghami.svg',
    'انغامي': 'site/img/brands/anghami.svg',
    'أنغامي': 'site/img/brands/anghami.svg',
    'youtube': 'site/img/brands/youtube.svg',
    'يوتيوب': 'site/img/brands/youtube.svg',

    # Social & Chat Apps
    'tiktok': 'site/img/brands/tiktok.svg',
    'تيك توك': 'site/img/brands/tiktok.svg',
    'تيكتوك': 'site/img/brands/tiktok.svg',
    'telegram premium': 'site/img/brands/telegram.svg',
    'telegram': 'site/img/brands/telegram.svg',
    'تيليجرام': 'site/img/brands/telegram.svg',
    'تليجرام': 'site/img/brands/telegram.svg',
    'تلغرام': 'site/img/brands/telegram.svg',
    'whatsapp': 'site/img/brands/whatsapp.svg',
    'واتساب': 'site/img/brands/whatsapp.svg',
    'واتس اب': 'site/img/brands/whatsapp.svg',
    'facebook': 'site/img/brands/facebook.svg',
    'فيسبوك': 'site/img/brands/facebook.svg',
    'فيس بوك': 'site/img/brands/facebook.svg',
    'instagram': 'site/img/brands/instagram.svg',
    'انستغرام': 'site/img/brands/instagram.svg',
    'انستقرام': 'site/img/brands/instagram.svg',
    'snapchat': 'site/img/brands/snapchat.svg',
    'سناب شات': 'site/img/brands/snapchat.svg',
    'twitter': 'site/img/brands/twitter_x.svg',
    'تويتر': 'site/img/brands/twitter_x.svg',
    'x / twitter': 'site/img/brands/twitter_x.svg',
    'discord': 'site/img/brands/discord.svg',
    'دسكورد': 'site/img/brands/discord.svg',
    'ديسكورد': 'site/img/brands/discord.svg',
    'bigo live': 'site/img/brands/bigo.svg',
    'bigo': 'site/img/brands/bigo.svg',
    'بيجو لايف': 'site/img/brands/bigo.svg',
    'بيجو': 'site/img/brands/bigo.svg',
    'likee': 'site/img/brands/likee.svg',
    'لايكي': 'site/img/brands/likee.svg',
    'tango live': 'site/img/brands/tango.svg',
    'tango': 'site/img/brands/tango.svg',
    'تانجو لايف': 'site/img/brands/tango.svg',
    'تانجو': 'site/img/brands/tango.svg',
    'imo chat': 'site/img/brands/imo.svg',
    'imo': 'site/img/brands/imo.svg',
    'إيمو شات': 'site/img/brands/imo.svg',
    'إيمو': 'site/img/brands/imo.svg',
    'ايمو': 'site/img/brands/imo.svg',
    'toptop': 'site/img/brands/toptop.svg',
    'توب توب': 'site/img/brands/toptop.svg',
    'poppo live': 'site/img/brands/poppo.svg',
    'poppo': 'site/img/brands/poppo.svg',
    'بوبو لايف': 'site/img/brands/poppo.svg',
    'بوبو': 'site/img/brands/poppo.svg',
    'mico live': 'site/img/brands/mico.svg',
    'mico': 'site/img/brands/mico.svg',
    'ميكو لايف': 'site/img/brands/mico.svg',
    'ميكو': 'site/img/brands/mico.svg',
    'chamet': 'site/img/brands/chamet.svg',
    'شاميت': 'site/img/brands/chamet.svg',
    'azar': 'site/img/brands/azar.svg',
    'آزار': 'site/img/brands/azar.svg',
    'ازار': 'site/img/brands/azar.svg',
    'livu': 'site/img/brands/livu.svg',
    'ليف يو': 'site/img/brands/livu.svg',
    'meyo live': 'site/img/brands/meyo.svg',
    'meyo': 'site/img/brands/meyo.svg',
    'ميو لايف': 'site/img/brands/meyo.svg',
    'ميو': 'site/img/brands/meyo.svg',
    'soul chill': 'site/img/brands/soul.svg',
    'soul star': 'site/img/brands/soul.svg',
    'soul': 'site/img/brands/soul.svg',
    'سول تشيل': 'site/img/brands/soul.svg',
    'سول': 'site/img/brands/soul.svg',

    # AI & Productivity
    'chatgpt': 'site/img/brands/chatgpt.svg',
    'openai': 'site/img/brands/chatgpt.svg',
    'شات جي بي تي': 'site/img/brands/chatgpt.svg',
    'gemini pro': 'site/img/brands/gemini.svg',
    'gemini': 'site/img/brands/gemini.svg',
    'جيميني': 'site/img/brands/gemini.svg',
    'جيميناي': 'site/img/brands/gemini.svg',
    'canva pro': 'site/img/brands/canva.svg',
    'canva': 'site/img/brands/canva.svg',
    'كانفا برو': 'site/img/brands/canva.svg',
    'كانفا': 'site/img/brands/canva.svg',
    'picsart gold': 'site/img/brands/picsart.svg',
    'picsart': 'site/img/brands/picsart.svg',
    'بيكس آرت': 'site/img/brands/picsart.svg',
    'بيكس ارت': 'site/img/brands/picsart.svg',
    'flaticon': 'site/img/brands/flaticon.svg',
    'فلات آيكون': 'site/img/brands/flaticon.svg',
    'فلاتيكون': 'site/img/brands/flaticon.svg',

    # Telecom & Balance
    'turkcell': 'site/img/brands/turkcell.svg',
    'تروكسل': 'site/img/brands/turkcell.svg',
    'توركسيل': 'site/img/brands/turkcell.svg',
    'turk telekom': 'site/img/brands/turktelekom.svg',
    'turktelekom': 'site/img/brands/turktelekom.svg',
    'ترك تليكوم': 'site/img/brands/turktelekom.svg',
    'تليكوم': 'site/img/brands/turktelekom.svg',
    'vodafone': 'site/img/brands/vodafone.svg',
    'فودافون': 'site/img/brands/vodafone.svg',
    'syriatel': 'site/img/brands/syriatel.svg',
    'سيريتل': 'site/img/brands/syriatel.svg',
    'سيرياتيل': 'site/img/brands/syriatel.svg',
    'mtn syria': 'site/img/brands/mtn.svg',
    'mtn': 'site/img/brands/mtn.svg',
    'ام تي ان': 'site/img/brands/mtn.svg',
    'إم تي إن': 'site/img/brands/mtn.svg',
    'stc': 'site/img/brands/stc.svg',
    'اس تي سي': 'site/img/brands/stc.svg',
    'سوا': 'site/img/brands/stc.svg',
    'zain': 'site/img/brands/zain.svg',
    'زين': 'site/img/brands/zain.svg',

    # VPN
    'nordvpn': 'site/img/brands/vpn.svg',
    'expressvpn': 'site/img/brands/vpn.svg',
    'surfshark': 'site/img/brands/vpn.svg',
    'lagofast': 'site/img/brands/vpn.svg',
    'vpn': 'site/img/brands/vpn.svg',
    'بروكسي': 'site/img/brands/vpn.svg',
}

DEFAULT_FALLBACK_SVG = 'site/img/brands/generic_digital.svg'

# Keys sorted by length descending so longer, more specific brand names always match first
_SORTED_BRAND_KEYS = sorted(BRAND_STATIC_SVG_MAP.keys(), key=lambda k: len(k), reverse=True)

def match_brand_static_asset(text):
    if not text:
        return None
    t = f" {text.lower()} "
    for brand in _SORTED_BRAND_KEYS:
        # For short Latin tokens (3 chars or less like mtn, stc, cod, psn), require word boundaries
        if len(brand) <= 3 and brand.isalnum() and not any(ord(c) > 127 for c in brand):
            pattern = rf"(?:\b|_){re.escape(brand)}(?:\b|_)"
            if re.search(pattern, t):
                return static(BRAND_STATIC_SVG_MAP[brand])
        else:
            if brand in t:
                return static(BRAND_STATIC_SVG_MAP[brand])
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
    1. Direct product media fields: image, thumbnail, cover_image (Highest Priority!
       This ensures the studio-branded card with authentic artwork + Raqamiyat verified badge is always displayed).
    2. Product metadata image URLs (Alkasr/Tafa3ol/SMM official API banner/icon fields).
    3. Category image.
    4. Database fallbacks (gallery, linked ProviderProduct, or parent product).
    5. Curated authentic brand static assets (only as safe fallback if no product image exists).
    6. High-end Raqamiyat brand luxury SVG fallback.
    """
    if not product:
        return static(DEFAULT_FALLBACK_SVG)

    # 1. ALWAYS PRIORITIZE actual product image file if present!
    try:
        for attr in ('image', 'thumbnail', 'cover_image'):
            val = getattr(product, attr, None)
            u = _extract_url_from_field(val)
            if u:
                return u
    except Exception:
        pass

    # 2. Check product metadata image fields (official provider banner / artwork)
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

    # 3. Category image
    cat = getattr(product, 'category', None)
    if cat:
        u = _extract_url_from_field(getattr(cat, 'image', None))
        if u:
            return u

    # 4. Database fallbacks (only if allow_db is True)
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

    # 5. Fallback: try authentic brand static asset only if no real image exists
    p_name = getattr(product, 'name', '')
    brand_asset = match_brand_static_asset(p_name)
    if brand_asset:
        return brand_asset

    # 6. Fallback to official Raqamiyat high-tech luxury brand emblem
    return static(DEFAULT_FALLBACK_SVG)


