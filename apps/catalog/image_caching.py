import os
import logging
from django.conf import settings
from django.templatetags.static import static

logger = logging.getLogger(__name__)

BRAND_STATIC_SVG_MAP = {
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
    'tiktok': 'site/img/brands/tiktok.svg',
    'tik tok': 'site/img/brands/tiktok.svg',
    'تيك توك': 'site/img/brands/tiktok.svg',
    'تيكتوك': 'site/img/brands/tiktok.svg',
    'netflix': 'site/img/brands/netflix.svg',
    'نتفلكس': 'site/img/brands/netflix.svg',
    'نتفليكس': 'site/img/brands/netflix.svg',
    'shahid': 'site/img/brands/shahid.svg',
    'شاهد': 'site/img/brands/shahid.svg',
    'telegram': 'site/img/brands/telegram.svg',
    'تيليجرام': 'site/img/brands/telegram.svg',
    'تليجرام': 'site/img/brands/telegram.svg',
    'تلغرام': 'site/img/brands/telegram.svg',
    'google play': 'site/img/brands/googleplay.svg',
    'google': 'site/img/brands/googleplay.svg',
    'جوجل بلاي': 'site/img/brands/googleplay.svg',
    'قوقل بلاي': 'site/img/brands/googleplay.svg',
    'itunes': 'site/img/brands/apple.svg',
    'apple': 'site/img/brands/apple.svg',
    'ابل': 'site/img/brands/apple.svg',
    'آبل': 'site/img/brands/apple.svg',
    'ايتونز': 'site/img/brands/apple.svg',
    'steam': 'site/img/brands/steam.svg',
    'ستيم': 'site/img/brands/steam.svg',
    'playstation': 'site/img/brands/playstation.svg',
    'بلايستيشن': 'site/img/brands/playstation.svg',
    'psn': 'site/img/brands/playstation.svg',
    'سوني': 'site/img/brands/playstation.svg',
    'xbox': 'site/img/brands/xbox.svg',
    'اكس بوكس': 'site/img/brands/xbox.svg',
    'إكس بوكس': 'site/img/brands/xbox.svg',
    'discord': 'site/img/brands/discord.svg',
    'دسكورد': 'site/img/brands/discord.svg',
    'ديسكورد': 'site/img/brands/discord.svg',
    'spotify': 'site/img/brands/spotify.svg',
    'سبوتيفاي': 'site/img/brands/spotify.svg',
    'سبوتفاي': 'site/img/brands/spotify.svg',
    'youtube': 'site/img/brands/youtube.svg',
    'يوتيوب': 'site/img/brands/youtube.svg',
    'snapchat': 'site/img/brands/snapchat.svg',
    'snap': 'site/img/brands/snapchat.svg',
    'سناب شات': 'site/img/brands/snapchat.svg',
    'سناب': 'site/img/brands/snapchat.svg',
    'chatgpt': 'site/img/brands/chatgpt.svg',
    'openai': 'site/img/brands/chatgpt.svg',
    'gpt': 'site/img/brands/chatgpt.svg',
    'شات جي بي تي': 'site/img/brands/chatgpt.svg',
    'ذكاء اصطناعي': 'site/img/brands/chatgpt.svg',
    'mobile legends': 'site/img/brands/mobilelegends.svg',
    'mobilelegends': 'site/img/brands/mobilelegends.svg',
    'موبايل ليجند': 'site/img/brands/mobilelegends.svg',
    'clash of clans': 'site/img/brands/clashofclans.svg',
    'clash royale': 'site/img/brands/clashofclans.svg',
    'clash': 'site/img/brands/clashofclans.svg',
    'كلاش': 'site/img/brands/clashofclans.svg',
    'bigo': 'site/img/brands/bigo.svg',
    'بيجو': 'site/img/brands/bigo.svg',
    'بيغو': 'site/img/brands/bigo.svg',
    'likee': 'site/img/brands/likee.svg',
    'لايكي': 'site/img/brands/likee.svg',
    'syriatel': 'site/img/brands/syriatel.svg',
    'سيريتل': 'site/img/brands/syriatel.svg',
    'سيرياتيل': 'site/img/brands/syriatel.svg',
    'ea fc': 'site/img/brands/cod.svg',
    'fifa': 'site/img/brands/cod.svg',
    'valorant': 'site/img/brands/valorant.svg',
    'فالورانت': 'site/img/brands/valorant.svg',
    'فالورنت': 'site/img/brands/valorant.svg',
    'call of duty': 'site/img/brands/cod.svg',
    'cod': 'site/img/brands/cod.svg',
    'كود': 'site/img/brands/cod.svg',
    'كول أوف ديوتي': 'site/img/brands/cod.svg',
    'canva': 'site/img/brands/canva.svg',
    'كانفا': 'site/img/brands/canva.svg',
    'vpn': 'site/img/brands/vpn.svg',
    'بروكسي': 'site/img/brands/vpn.svg',
    'nordvpn': 'site/img/brands/vpn.svg',
    'expressvpn': 'site/img/brands/vpn.svg',
    'kaspersky': 'site/img/brands/vpn.svg',
    'adguard': 'site/img/brands/vpn.svg',
    'browsec': 'site/img/brands/vpn.svg',
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

def get_product_image_url(product):
    if not product:
        return static(DEFAULT_FALLBACK_SVG)

    img = getattr(product, 'image', None)
    if img:
        try:
            if hasattr(img, 'url') and img.url:
                url_str = str(img.url)
                if 'wikimedia.org' not in url_str and 'seeklogo.com' not in url_str:
                    return url_str
        except Exception:
            pass

    thumb = getattr(product, 'thumbnail', None)
    if thumb:
        try:
            if hasattr(thumb, 'url') and thumb.url:
                url_str = str(thumb.url)
                if 'wikimedia.org' not in url_str and 'seeklogo.com' not in url_str:
                    return url_str
        except Exception:
            pass

    cover = getattr(product, 'cover_image', None)
    if cover:
        try:
            if hasattr(cover, 'url') and cover.url:
                url_str = str(cover.url)
                if 'wikimedia.org' not in url_str and 'seeklogo.com' not in url_str:
                    return url_str
        except Exception:
            pass

    try:
        gallery_mgr = getattr(product, 'gallery', None)
        if gallery_mgr:
            first_gal = gallery_mgr.first()
            if first_gal and getattr(first_gal, 'url', None):
                return first_gal.url
    except Exception:
        pass

    p_name = getattr(product, 'name', '')
    brand_asset = match_brand_static_asset(p_name)
    if brand_asset:
        return brand_asset

    cat = getattr(product, 'category', None)
    if cat:
        if getattr(cat, 'image', None):
            try:
                if hasattr(cat.image, 'url') and cat.image.url:
                    return cat.image.url
            except Exception:
                pass
        cat_name = getattr(cat, 'name', '')
        cat_asset = match_brand_static_asset(cat_name)
        if cat_asset:
            return cat_asset

    return static(DEFAULT_FALLBACK_SVG)

