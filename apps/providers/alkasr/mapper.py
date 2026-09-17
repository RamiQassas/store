import logging
from decimal import Decimal
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant, Category

logger = logging.getLogger(__name__)

COMMON_TRANSLATIONS = {
    "chat": "شات",
    "live": "لايف",
    "party": "بارتي",
    "voice": "صوتي",
    "room": "غرف",
    "card": "بطاقة",
    "cards": "بطاقات",
    "balance": "رصيد",
    "blance": "رصيد",
    "coins": "كوينز",
    "coin": "كوينز",
    "gems": "جواهر",
    "diamonds": "مجوهرات",
    "points": "نقاط",
    "plus": "بلس",
    "vip": "VIP",
    "pro": "برو",
    "vpn": "في بي ان",
    "cash": "كاش",
    "pay": "دفع",
    "store": "ستور",
    "app": "تطبيق",
    "teklifler": "عروض",
    "paketler": "باقات",
    "aylik": "شهرية",
    "aylık": "شهرية",
}

KNOWN_NAMES = {
    "pubg": ("ببجي موبايل", "PUBG Mobile UC"),
    "free fire": ("فري فاير", "Free Fire Diamonds"),
    "فايتر": ("فري فاير", "Free Fire Diamonds"),
    "roblox": ("روبلوكس", "Roblox Robux"),
    "roblex": ("روبلوكس", "Roblox Robux"),
    "jawaker": ("جواكر", "Jawaker Tokens"),
    "clash of clans": ("كلاش اوف كلانس", "Clash of Clans"),
    "clash royale": ("كلاش رويال", "Clash Royale"),
    "mobile legends": ("موبايل ليجندز", "Mobile Legends Diamonds"),
    "brawl stars": ("براول ستارز", "Brawl Stars Gems"),
    "genshin impact": ("جينشين امباكت", "Genshin Impact Genesis"),
    "genshin": ("جينشين امباكت", "Genshin Impact Genesis"),
    "ea fc": ("فيفا / اف سي موبايل", "EA FC Mobile Points"),
    "fifa": ("فيفا موبايل", "FIFA Mobile"),
    "call of duty": ("كول اوف ديوتي موبايل", "Call of Duty Mobile CP"),
    "cod": ("كول اوف ديوتي موبايل", "Call of Duty Mobile CP"),
    "valorant": ("فالورانت", "Valorant Points"),
    "league of legends": ("ليج اوف ليجيندز", "League of Legends RP"),
    "lol": ("ليج اوف ليجيندز", "League of Legends RP"),
    "honor of kings": ("اونور اوف كينجز", "Honor of Kings Tokens"),
    "toptop": ("توب توب", "TopTop Coins"),
    "yalla ludo": ("يلا لودو", "Yalla Ludo Diamonds"),
    "tiktok": ("تيك توك", "TikTok Coins"),
    "telegram": ("تيليجرام بريميوم", "Telegram Premium"),
    "netflix": ("نتفلكس", "Netflix"),
    "shahid": ("شاهد VIP", "Shahid VIP"),
    "discord": ("دسكورد نيترو", "Discord Nitro"),
    "spotify": ("سبوتيفاي بريميوم", "Spotify Premium"),
    "youtube": ("يوتيوب بريميوم", "YouTube Premium"),
    "snapchat": ("سناب شات بلس", "Snapchat Plus"),
    "chatgpt": ("شات جي بي تي", "ChatGPT Plus"),
    "openai": ("شات جي بي تي", "OpenAI ChatGPT"),
    "bigo": ("بيجو لايف", "Bigo Live Diamonds"),
    "likee": ("لايكي", "Likee Diamonds"),
    "soulchill": ("سول تشيل", "Soulchill Crystals"),
    "yoyo": ("يويو شات", "YoYo Chat Coins"),
    "chamet": ("شاميت", "Chamet Diamonds"),
    "poppo": ("بوبو لايف", "Poppo Live Coins"),
    "livu": ("ليف يو", "LivU Coins"),
    "tango": ("تانغو لايف", "Tango Live Coins"),
    "mico": ("ميكو ورلد", "MICO World Coins"),
    "ometv": ("اومي تي في", "OmeTV VIP"),
    "bobo": ("بوبو شات", "Bobo Chat Coins"),
    "4fun": ("فور فن شات", "4Fun Chat"),
    "4party": ("فور بارتي شات", "4Party Chat"),
    "ahlan": ("أهلاً شات", "Ahlan Chat"),
    "azal": ("ازال لايف", "Azal Live"),
    "allo": ("الو شات", "Allo Chat"),
    "amar": ("قمر شات", "Amar Chat"),
    "amisu": ("اميسو بارتي", "Amisu Party"),
    "amo": ("امو شات", "Amo Chat"),
    "aria": ("آريا شات", "Aria Chat"),
    "google play": ("بطاقات جوجل بلاي", "Google Play Cards"),
    "itunes": ("بطاقات ابل ايتونز", "Apple iTunes Cards"),
    "apple": ("بطاقات ابل ستور", "Apple Store Cards"),
    "steam": ("بطاقات ستيم", "Steam Wallet"),
    "playstation": ("بطاقات بلايستيشن", "PlayStation Store"),
    "psn": ("بطاقات بلايستيشن", "PlayStation Network"),
    "xbox": ("بطاقات اكس بوكس", "Xbox Live & Game Pass"),
    "syriatel": ("سيريتل كاش", "Syriatel Cash"),
    "mtn": ("ام تي ان كاش", "MTN Cash"),
    "asiacell": ("رصيد اسياسيل", "Asiacell Balance"),
    "zain": ("رصيد زين", "Zain Balance"),
    "korek": ("رصيد كورك", "Korek Balance"),
    "turkcell": ("رصيد تركسل", "Turkcell Balance"),
    "vodafone": ("رصيد فودافون", "Vodafone Balance"),
    "adguard": ("ادجارد في بي ان", "AdGuard VPN"),
    "nordvpn": ("نورد في بي ان", "NordVPN"),
    "expressvpn": ("اكسبريس في بي ان", "ExpressVPN"),
    "kaspersky": ("كاسبرسكي انتي فايروس", "Kaspersky Antivirus"),
}

from apps.catalog.naming import format_bilingual_name



class AlkasrMapperService:
    def __init__(self, profile):
        self.profile = profile

    def _get_category_chain(self, pp):
        """
        Returns the category hierarchy list from root ancestor down to leaf:
        [Root_Section, Application_or_Brand, Subcategory_or_Method]
        """
        chain = []
        curr = getattr(pp, 'category', None)
        seen = set()
        while curr and curr.remote_id not in seen:
            seen.add(curr.remote_id)
            chain.append(curr)
            curr = curr.parent
        chain.reverse()
        return chain

    def _get_group_name(self, pp):
        raw = self._get_raw_group_name(pp)
        return format_bilingual_name(raw)

    def _get_raw_group_name(self, pp):
        """
        Determines the canonical parent Product name (Application / Service / Brand),
        e.g. ببجي موبايل (PUBG Global), فري فاير (Free Fire), سيريتل (Syriatel), نتفلكس (Netflix).
        Prevents fragmentation, duplicate products, and country-split entries.
        """
        import re
        generic_names = {
            "null", "none", "games", "live application", "data and communication", 
            "gift cards", "tv services", "money transfers", "social media", 
            "numbers and accounts", "program activation numbers", "ألعاب", "عام",
            "شحن الألعاب", "شحن التطبيقات", "رصيد الهاتف", "تفعيل الأرقام المؤقتة",
            "ترويج ودعم السوشيال ميديا", "بطاقات الهدايا", "العملات الرقمية", "default",
            "قسم الألعاب", "قسم الدردشة", "قسم الأرصدة", "قسم الأرصدة والاتصالات",
            "البطاقات الالكترونية", "البطاقات الإلكترونية", "خدمات التلفاز", "الأرقام والحسابات",
            "الذكاء الاصطناعي", "قسم التصميم", "اشتراكات vpn", "1370", "1332", "1350", "code"
        }

        p_name = (pp.name or "").strip()
        c_name = (pp.category.name if pp.category else "").strip()
        parent_name = (pp.category.parent.name if pp.category and pp.category.parent else "").strip()
        cat_remote = str(getattr(pp.category, 'remote_id', '') or '').strip()
        cat_parent_remote = str(getattr(pp.category, 'parent_remote_id', '') or '').strip()

        combined = f"{p_name} {c_name} {parent_name}".lower()

        # 1. PUBG Global vs Turkey
        if "pubg" in combined or "ببجي" in combined or "uc" in combined or cat_remote == "1332" or "red package" in combined:
            if any(k in combined for k in ("turkey", "تركي", " tr", "tr ", "tr/")):
                return "ببجي موبايل تركيا (PUBG TR)"
            return "ببجي موبايل (PUBG Global)"

        # 2. Free Fire
        if "free fire" in combined or "فري فاير" in combined:
            return "فري فاير (Free Fire)"

        # 3. Roblox (merge all countries & cards into one)
        if "roblox" in combined or "roblex" in combined or "روبلوكس" in combined:
            return "روبلوكس (Roblox)"

        # 4. Jawaker
        if "jawaker" in combined or "جواكر" in combined:
            return "جواكر (Jawaker)"

        # 5. Mobile Legends
        if "mobile legends" in combined or "موبايل ليجند" in combined:
            return "موبايل ليجندز (Mobile Legends)"

        # 6. Clash Royale & Clash of Clans
        if "clash royale" in combined or "كلاش رويال" in combined:
            return "كلاش رويال (Clash Royale)"
        if "clash of clans" in combined or "كلاش أوف كلانس" in combined:
            return "كلاش أوف كلانس (Clash of Clans)"

        # 7. WePlay
        if "weplay" in combined or "وي بلاي" in combined:
            return "وي بلاي (WePlay)"

        # 8. Yalla Ludo
        if "yalla ludo" in combined or "يلا لودو" in combined or "ludo diamond" in combined:
            return "يلا لودو (Yalla Ludo)"

        # 9. PlayStation (merge all regions: Bahrain, Kuwait, USA, KSA, UAE, etc.)
        if "playstation" in combined or "بلايستيشن" in combined or "psn" in combined or re.search(r'\bps\s+(usa|ksa|uae|uk|ger|bah|kwt|canada|fransa|germany|italy|japan|oman|qatar|spain|bahrain|kuwait)', combined):
            return "بطاقات بلايستيشن (PlayStation)"

        # 10. iTunes / Apple (merge all regions into one canonical app)
        if "itunes" in combined or "آيتونز" in combined or "ايتونز" in combined or ("apple" in combined and "card" in combined):
            return "بطاقات أبل / آيتونز (iTunes)"

        # 11. Google Play (merge all regions)
        if "google play" in combined or "جوجل بلاي" in combined:
            return "بطاقات جوجل بلاي (Google Play)"

        # 12. Steam (merge sudi, usa, global)
        if "steam" in combined or "ستيم" in combined or ("sudi" in combined and any(x in combined for x in ("20", "100", "card"))) or ("usa" in combined and "5" in combined):
            return "بطاقات ستيم (Steam)"

        # 13. Razer Gold
        if "razer" in combined or "ريزر" in combined:
            return "بطاقات ريزر جولد (Razer Gold)"

        # 14. Syriatel
        if "syriatel" in combined or "سيريتل" in combined or "سيريتيل" in combined:
            if any(k in combined for k in ("حوالات", "تحويلات", "transfer")):
                return "سيريتل كاش (تحويلات مالية)"
            return "سيريتل (Syriatel)"

        # 15. MTN
        if "mtn" in combined or "ام تي ان" in combined:
            return "ام تي ان (MTN)"

        # 16. Turkcell, Telekom, Vodafone
        if "turkcell" in combined or "تروكسل" in combined or "nar paket" in combined or "kolay paket" in combined:
            return "تروكسل تركيا (Turkcell)"
        if "telekom" in combined or "تليكوم" in combined:
            return "ترك تليكوم تركيا (Türk Telekom)"
        if "vodafone" in combined or "فودافون" in combined:
            return "فودافون تركيا (Vodafone)"
        if "selam" in combined or "سلام تليكوم" in combined:
            return "سلام تليكوم (Selam)"
        if "wi-fi" in combined or "واي فاي" in combined or "cep magnet" in combined:
            return "باقات إنترنت واي فاي (Wi-Fi)"
        if "hgs" in combined:
            return "شحن HGS الطرق السريعة تركيا"

        # 17. TikTok (split currencies vs social media services)
        if "tiktok" in combined or "تيك توك" in combined or "tik yok" in combined:
            if any(x in combined for x in ("متابعين", "لايكات", "مشاهدات", "تعليقات", "followers", "likes", "views", "shares")):
                return "خدمات تيك توك (TikTok Services)"
            return "تيك توك (TikTok)"

        # 18. Social Media Services
        if "instagram" in combined or "انستغرام" in combined or "انستا" in combined:
            return "خدمات إنستغرام (Instagram)"
        if "facebook" in combined or "فيسبوك" in combined or "فيس بوك" in combined:
            return "خدمات فيسبوك (Facebook)"
        if "twitter" in combined or "تويتر" in combined:
            return "خدمات تويتر / X (Twitter)"
        if "youtube" in combined or "يوتيوب" in combined:
            return "خدمات يوتيوب (YouTube)"
        if "telegram" in combined or "تليجرام" in combined or "تلغرام" in combined:
            if "premium" in combined or "بريميوم" in combined:
                return "تليجرام بريميوم (Telegram Premium)"
            return "تفعيل أرقام تليجرام (Telegram)"

        # 19. WhatsApp
        if "whatsapp" in combined or "واتساب" in combined or "واتس اب" in combined or cat_remote == "1350":
            return "تفعيل أرقام واتساب (WhatsApp)"

        # 20. Streaming / TV
        if "netflix" in combined or "نتفلكس" in combined or "نتفليكس" in combined:
            return "نتفلكس (Netflix)"
        if "shahid" in combined or "شاهد" in combined:
            return "شاهد VIP (Shahid VIP)"
        if "osn" in combined:
            return "او اس ان بلس (OSN+)"
        if "disney" in combined or "ديزني" in combined:
            return "ديزني بلس (Disney+)"
        if "blue 4k" in combined or "بلو فور كي" in combined:
            return "بلو فور كي (BLUE 4K IPTV)"
        if "shamna" in combined or "شامنا" in combined:
            return "شامنا تي في (Shamna TV)"
        if "zain tv" in combined or "زين تي في" in combined:
            return "زين تي في (Zain TV)"
        if "barakat" in combined or "بركات" in combined:
            return "بركات تي في (Barakat TV)"
        if "tango pro" in combined or "تانجو برو" in combined:
            return "تانجو برو (Tango Pro)"

        # 21. Chat & Live Apps
        if "soul" in combined or "سول" in combined:
            return "سول (Soul App)"
        if "lions" in combined or "ليونس" in combined:
            return "لايونز شات (Lions Chat)"
        if "siya" in combined or "سيا" in combined:
            return "سيا (Siya)"
        if "yalla live" in combined or "يلا لايف" in combined:
            return "يلا لايف (Yalla Live)"
        if "azar" in combined or "أزار" in combined:
            return "أزار شات (Azar Chat)"
        if "bigo" in combined or "بيجو" in combined:
            return "بيجو لايف (Bigo Live)"
        if "likee" in combined or "لايكي" in combined:
            return "لايكي (Likee)"
        if "imo" in combined or "إيمو" in combined or "ايمو" in combined:
            return "إيمو شات (IMO Chat)"
        if "livu" in combined or "لايف يو" in combined or "ليف يو" in combined:
            return "ليف يو (LivU)"
        if "meyo" in combined or "ميو لايف" in combined:
            return "ميو لايف (Meyo Live)"
        if "party star" in combined or "بارتي ستار" in combined:
            return "بارتي ستار (Party Star)"
        if "tumile" in combined or "تومي" in combined:
            return "تومي (Tumile)"
        if "mixu" in combined or "ميكس يو" in combined:
            return "ميكس يو (Mixu)"
        if "bermuda" in combined or "برمودا" in combined:
            return "برمودا (Bermuda Chat)"
        if "hi cat" in combined or "هاي كات" in combined:
            return "هاي كات (Hi Cat)"
        if "star lite" in combined or "ستار لايت" in combined:
            return "ستار لايت (Star Lite)"
        if "zepeto" in combined or "زيبيتو" in combined:
            return "زيبيتو (Zepeto)"
        if "snapchat" in combined or "سناب شات" in combined or cat_remote == "1370":
            return "سناب شات بلس (Snapchat Plus)"

        # 22. AI & Software
        if "gemini" in combined or "جيميني" in combined:
            return "جيميني برو (Gemini Pro AI)"
        if "canva" in combined or "كانفا" in combined:
            return "كانفا برو (Canva Pro)"
        if "picsart" in combined or "بيكس آرت" in combined:
            return "بيكس آرت (Picsart)"
        if "perplexity" in combined:
            return "Perplexity Pro"
        if "gamma" in combined:
            return "Gamma AI Pro"

        # 23. VPN
        if "adguard" in combined:
            return "ADguard VPN"
        if "browsec" in combined:
            return "Browsec VPN"
        if "cyber ghost" in combined or "cyberghost" in combined:
            return "Cyber Ghost VPN"
        if "express vpn" in combined or "expressvpn" in combined:
            return "Express VPN"
        if "hotspot" in combined:
            return "اشتراكات Hotspot Shield"
        if "lagofast" in combined:
            return "اشتراكات LagoFast"
        if "nord" in combined:
            return "Nord VPN"
        if "proton" in combined:
            return "Proton VPN"
        if "surfshark" in combined:
            return "Surfshark VPN"
        if "pure vpn" in combined:
            return "Pure VPN Premium"
        if "windscribe" in combined:
            return "Windscribe Traffic VPN"
        if "ipvanish" in combined:
            return "IPVanish VPN"
        if "zoog" in combined:
            return "Zoog VPN"
        if "pia vpn" in combined:
            return "PIA VPN"
        if "open vpn" in combined or "openvpn" in combined:
            return "Open VPN"
        if "tunnelbar" in combined or "tunnelbear" in combined:
            return "TunnelBar VPN"
        if "planet vpn" in combined:
            return "Planet VPN"

        # 24. Money transfers
        if any(k in combined for k in ("حوالات", "شام كاش", "الهرم", "محافظ", "بنوك")):
            if c_name and c_name.lower() not in generic_names:
                return c_name
            if p_name and p_name.lower() not in generic_names:
                return p_name

        # 25. Fallback cleanly to category or clean product name
        if c_name and c_name.lower() not in generic_names:
            return c_name
        if parent_name and parent_name.lower() not in generic_names:
            return parent_name
        
        clean = re.sub(r'[\d\+\$].*', '', p_name).strip()
        clean = re.sub(r'(\s*-\s*|\s*_\s*)$', '', clean).strip()
        if len(clean) >= 3 and clean.lower() not in generic_names:
            return clean

        return p_name or "خدمة عامة"

    def _get_store_category(self, pp, store, group_name=""):
        """
        Determines the main Store Section (Category) which is STRICTLY one of the canonical sections:
        - شحن الألعاب
        - شحن التطبيقات
        - اتصالات ورصيد
        - بطاقات رقمية
        - خدمات التلفزيون والبث
        - أرقام وحسابات
        - اشتراكات VPN
        - الذكاء الاصطناعي
        - برامج وتصميم
        - تحويلات مالية
        - ترويج ودعم السوشيال ميديا
        """
        section_sort_order = {
            "شحن الألعاب": 1,
            "شحن التطبيقات": 2,
            "اتصالات ورصيد": 3,
            "بطاقات رقمية": 4,
            "خدمات التلفزيون والبث": 5,
            "أرقام وحسابات": 6,
            "اشتراكات VPN": 7,
            "الذكاء الاصطناعي": 8,
            "برامج وتصميم": 9,
            "تحويلات مالية": 10,
            "ترويج ودعم السوشيال ميديا": 11,
        }

        g_low = (group_name or self._get_group_name(pp)).lower()
        p_low = f"{g_low} {pp.name or ''}".lower()

        # 1. Direct App Mapping based on verified group_name
        if any(k in g_low for k in ("ببجي", "pubg", "فري فاير", "free fire", "روبلوكس", "roblox", "جواكر", "jawaker", "موبايل ليجند", "mobile legends", "كلاش", "clash", "وي بلاي", "weplay", "valorant", "fortnite", "call of duty")):
            target_name = "شحن الألعاب"
        elif any(k in g_low for k in ("خدمات تيك توك", "خدمات إنستغرام", "خدمات فيسبوك", "خدمات تويتر", "خدمات يوتيوب", "سوشيال ميديا", "social media")) or any(k in p_low for k in ("متابعين", "لايكات", "مشاهدات", "followers", "likes", "views")):
            target_name = "ترويج ودعم السوشيال ميديا"
        elif any(k in g_low for k in ("سيريتل كاش (تحويلات مالية)", "شام كاش", "حوالات", "الهرم", "محافظ", "بنوك")):
            target_name = "تحويلات مالية"
        elif any(k in g_low for k in ("سيريتل", "syriatel", "mtn", "ام تي ان", "تروكسل", "turkcell", "تليكوم", "telekom", "فودافون", "vodafone", "سلام", "selam", "واي فاي", "wi-fi", "hgs", "آسيا سيل", "asiacell")):
            target_name = "اتصالات ورصيد"
        elif any(k in g_low for k in ("بلايستيشن", "playstation", "آيتونز", "itunes", "جوجل بلاي", "google play", "ستيم", "steam", "ريزر", "razer", "بطاقات", "visa", "فيزا", "إكس بوكس", "xbox")):
            target_name = "بطاقات رقمية"
        elif any(k in g_low for k in ("نتفلكس", "netflix", "شاهد", "shahid", "osn", "ديزني", "disney", "بلو فور كي", "blue 4k", "شامنا", "shamna", "زين تي في", "zain", "بركات", "barakat", "تانجو برو", "tango pro", "ip tv", "tv")):
            target_name = "خدمات التلفزيون والبث"
        elif any(k in g_low for k in ("واتساب", "whatsapp", "تليجرام", "telegram", "أرقام", "ارقام", "accounts", "حسابات جاهزة")):
            target_name = "أرقام وحسابات"
        elif any(k in g_low for k in ("vpn", "hotspot", "lagofast", "surfshark", "nord", "proton", "express")):
            target_name = "اشتراكات VPN"
        elif any(k in g_low for k in ("جيميني", "gemini", "perplexity", "gamma", "ذكاء", "ai", "chatgpt", "gpt")):
            target_name = "الذكاء الاصطناعي"
        elif any(k in g_low for k in ("كانفا", "canva", "بيكس آرت", "picsart", "flaticon", "تصميم", "برامج", "رد تلقائي", "auto reply")):
            target_name = "برامج وتصميم"
        elif any(k in g_low for k in ("تيك توك", "tiktok", "يلا لودو", "yalla", "بيجو", "bigo", "لايكي", "likee", "إيمو", "imo", "ليف يو", "livu", "أزار", "azar", "سول", "soul", "تومي", "tumile", "ميكس يو", "mixu", "هاي كات", "بارتي", "party", "دردشة", "شات", "chat", "live", "لايف", "سناب شات", "snapchat", "لايونز", "lions")):
            target_name = "شحن التطبيقات"
        else:
            target_name = "شحن التطبيقات"

        sort_order = section_sort_order.get(target_name, 50)
        cat_obj, _ = Category.objects.get_or_create(
            store=store,
            name=target_name,
            defaults={"is_active": True, "sort_order": sort_order}
        )
        return cat_obj

    def map_all_to_catalog(self, products_qs=None, selected_group_names=None):
        """
        Batch map provider products into main store catalog.
        - Groups packages belonging to the same service under 1 Product with multiple ProductVariants (باقات).
        - Automatically organizes products under top-level Categories.
        - Sets accurate prices, costs, margins, and requirements.
        """
        import re
        if products_qs is None:
            products_qs = ProviderProduct.objects.filter(profile=self.profile, is_active=True)

        # Clean up any dot/placeholder products from previous runs
        Product.objects.filter(api_provider="tafa3olcard", name__regex=r'^[\.\s\-_=~*#]+$').delete()
        ProviderProduct.objects.filter(profile=self.profile, name__regex=r'^[\.\s\-_=~*#]+$').delete()

        # Deactivate any variants whose provider product is disabled, inactive, or deleted
        try:
            from django.db.models import Q
            inactive_remote_ids = list(
                ProviderProduct.objects.filter(profile=self.profile)
                .filter(Q(is_active=False) | Q(local_is_active=False))
                .values_list('remote_id', flat=True)
            )
            if inactive_remote_ids:
                int_pids = [int(x) for x in inactive_remote_ids if str(x).isdigit()]
                sku_patterns = [f"PRV-{self.profile.id}-{x}" for x in inactive_remote_ids]

                # Deactivate platform variants
                ProductVariant.objects.filter(
                    Q(sku__in=sku_patterns) | Q(api_product_id__in=int_pids)
                ).update(is_active=False, is_temporarily_disabled=True)

                # Deactivate sub-store cloned variants
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    for rid in inactive_remote_ids:
                        ProductVariant.all_objects.filter(
                            sku__icontains=f"-{rid}"
                        ).update(is_active=False, is_temporarily_disabled=True)
        except Exception as inact_err:
            logger.warning(f"Error deactivating inactive variants: {inact_err}")
            
        products_list = list(products_qs.select_related('category', 'category__parent', 'pricing').prefetch_related('parameters'))
        store = self.profile.store

        provider_code = "tafa3olcard" if ("tafa3ol" in (self.profile.base_url or "").lower() or "تفاعل" in (self.profile.provider_name or "").lower()) else "alkasr"

        # Group provider products by main service name (e.g. PUBG Mobile, Free Fire, Syriatel, MTN)
        grouped_products = {}
        for pp in products_list:
            p_name = (pp.name or "").strip()
            c_name = (pp.category.name if pp.category else "").strip()
            if (not p_name or p_name.lower() in ("null", "none", "undefined")) and \
               (not c_name or c_name.lower() in ("null", "none", "undefined")):
                continue

            if re.match(r'^[\.\s\-_=~*#]+$', p_name) or len(p_name) < 2:
                continue

            group_name = self._get_group_name(pp)
            if re.match(r'^[\.\s\-_=~*#]+$', group_name) or len(group_name) < 2:
                continue

            if selected_group_names:
                matched = False
                for sel in selected_group_names:
                    sel_s = (sel or "").strip().lower()
                    g_s = group_name.strip().lower()
                    if sel_s == g_s or sel_s in g_s or g_s in sel_s:
                        matched = True
                        break
                    sel_parts = [p.strip().lower() for p in sel_s.split("|") if p.strip()]
                    g_parts = [p.strip().lower() for p in g_s.split("|") if p.strip()]
                    if any(sp in g_parts or any(sp in gp for gp in g_parts) for sp in sel_parts):
                        matched = True
                        break
                if not matched:
                    continue
            grouped_products.setdefault(group_name, []).append(pp)

        for group_name, p_items in grouped_products.items():
            try:
                with transaction.atomic():
                    # Find or create store category for this group
                    store_category = self._get_store_category(p_items[0], store, group_name)

                    # Check if Product already exists for this group
                    local_product = Product.objects.filter(
                        store=store,
                        name=group_name[:255]
                    ).first()

                    # Find any image URL
                    img_url = ""
                    for item_p in p_items:
                        item_data = getattr(item_p, "data", None)
                        if item_data and isinstance(item_data, dict) and item_data.get("image_url"):
                            img_url = item_data["image_url"]
                            break

                    # Build combined parameters form_schema for this product
                    schema_fields = {}
                    for pp in p_items:
                        for param in pp.parameters.all():
                            if param.name not in schema_fields:
                                schema_fields[param.name] = {
                                    "name": param.name,
                                    "label": param.label,
                                    "type": param.parameter_type,
                                    "required": param.required
                                }

                    # Intelligent Field Fallback if provider did not return explicit input parameters
                    if not schema_fields:
                        cat_title = store_category.name if store_category else ""
                        g_lower = f"{group_name} {cat_title}".lower()
                        if any(k in g_lower for k in ("ألعاب", "game", "pubg", "ببجي", "free fire", "فري فاير", "roblox", "روبلوكس", "jawaker", "جواكر", "mobile legends", "كلاش", "clash", "cod", "fortnite", "valorant")):
                            schema_fields["playerId"] = {
                                "name": "playerId",
                                "label": "معرّف اللاعب (Player ID)",
                                "type": "text",
                                "required": True
                            }
                            if "mobile legends" in g_lower or "ليجند" in g_lower:
                                schema_fields["zoneId"] = {
                                    "name": "zoneId",
                                    "label": "معرّف السيرفر (Zone ID)",
                                    "type": "text",
                                    "required": True
                                }
                        elif any(k in g_lower for k in ("اتصالات", "رصيد", "syriatel", "سيريتل", "mtn", "ام تي ان", "تروكسل", "turkcell", "telekom", "تليكوم", "vodafone", "فودافون")):
                            schema_fields["phone_number"] = {
                                "name": "phone_number",
                                "label": "رقم الهاتف / الحساب المستلم",
                                "type": "text",
                                "required": True
                            }
                        elif any(k in g_lower for k in ("سوشيال", "social", "متابعين", "followers", "لايكات", "likes", "مشاهدات", "views", "تيك توك", "tiktok")):
                            schema_fields["link"] = {
                                "name": "link",
                                "label": "رابط الحساب أو المنشور (Link / URL)",
                                "type": "url",
                                "required": True
                            }
                        elif any(k in g_lower for k in ("تطبيقات", "دردشة", "شات", "chat", "live", "لايف", "bigo", "بيجو", "likee", "لايكي", "yalla", "يلا", "toptop", "توب توب")):
                            schema_fields["playerId"] = {
                                "name": "playerId",
                                "label": "معرّف الحساب في التطبيق (User ID)",
                                "type": "text",
                                "required": True
                            }

                    schema = {"version": 1, "fields": list(schema_fields.values())}

                    prod_meta = dict(local_product.metadata or {}) if local_product else {}
                    if img_url:
                        prod_meta["image_url"] = img_url

                    if not local_product:
                        local_product = Product.objects.create(
                            store=store,
                            name=group_name[:255],
                            category=store_category,
                            is_active=True,
                            is_out_of_stock=False,
                            track_inventory=False,
                            quantity=999999,
                            is_api_product=True,
                            api_provider=provider_code,
                            description=p_items[0].local_description or "",
                            form_schema=schema,
                            metadata=prod_meta
                        )
                    else:
                        if store and local_product.store != store:
                            local_product.store = store
                        if not local_product.category or local_product.category != store_category:
                            local_product.category = store_category
                        local_product.is_active = True
                        local_product.is_out_of_stock = False
                        local_product.track_inventory = False
                        local_product.quantity = 999999
                        local_product.is_api_product = True
                        local_product.api_provider = provider_code
                        if schema_fields:
                            local_product.form_schema = schema
                        if prod_meta:
                            local_product.metadata = prod_meta
                        local_product.save()

                    # Note: Automatic branding disabled so images are generated only on explicit button click

                    # Map each ProviderProduct as a ProductVariant (باقة) inside this single Product
                    for pp in p_items:
                        mapping = ProviderMapping.objects.filter(provider_product=pp).first()
                        if not mapping:
                            mapping = ProviderMapping(provider_product=pp)

                        mapping.local_product = local_product



                        # Extract and clean variant name first
                        variant_name = (pp.local_name or "").strip()
                        if not variant_name or variant_name.lower() in ("null", "none", "undefined", "false"):
                            variant_name = (pp.name or "").strip()
                        if not variant_name or variant_name.lower() in ("null", "none", "undefined", "false"):
                            if pp.category and pp.category.name and pp.category.name.strip().lower() not in ("null", "none"):
                                variant_name = pp.category.name.strip()
                            elif hasattr(pp, 'data') and isinstance(pp.data, dict) and pp.data.get("title") and str(pp.data.get("title")).lower() not in ("null", "none"):
                                variant_name = str(pp.data.get("title")).strip()
                            elif hasattr(pp, 'data') and isinstance(pp.data, dict) and pp.data.get("country"):
                                variant_name = f"تفعيل {pp.data.get('country')}"
                            else:
                                continue

                        # Determine quantity type from product_type stored during sync
                        # This mirrors exactly what the API spec says:
                        # - product_type=="package" (qty_values=null) → fixed, qty=1
                        # - product_type=="fixed_quantities" (qty_values=[list]) → list
                        # - product_type=="amount" (qty_values={min,max}) → range
                        qty_min = getattr(pp, 'qty_min', None)
                        try:
                            qty_min = int(qty_min) if qty_min is not None else None
                        except (ValueError, TypeError):
                            qty_min = None

                        qty_max = getattr(pp, 'qty_max', None)
                        try:
                            qty_max = int(qty_max) if qty_max is not None else None
                        except (ValueError, TypeError):
                            qty_max = None

                        raw_qty_list = getattr(pp, 'qty_list', None) or []
                        qty_list = [str(x).strip() for x in raw_qty_list if x is not None and str(x).strip().lower() not in ("none", "null", "")]

                        if pp.product_type == "fixed_quantities" or (qty_list and len(qty_list) > 0):
                            qty_type = "list"
                        elif pp.product_type == "amount" or (qty_min is not None and qty_max is not None and qty_max > qty_min and qty_max > 1):
                            qty_type = "range"
                        else:
                            qty_type = "fixed"

                        # Prices are stored as per-unit from the API — no multiplication needed
                        pricing = getattr(pp, 'pricing', None)
                        final_price = pricing.final_price if pricing else pp.cost_price
                        wholesale_price = pricing.final_wholesale_price if pricing else pp.cost_price
                        vip_price = pricing.final_vip_price if pricing else pp.cost_price
                        variant_cost = pp.cost_price

                        # Check if product is SMM per-mille and not yet divided by 1000
                        remote_id_str = str(pp.remote_id).strip()
                        cat_lower = str(pp.category.name if pp.category else "").lower()
                        name_lower = (pp.name or "").lower()
                        is_smm = (
                            remote_id_str in ("9364", "7346", "7350", "7354", "7359", "7370", "7373", "7377")
                            or (qty_type == "range" and (qty_min or 0) >= 1000 and variant_cost >= Decimal("0.50"))
                            or (any(k in cat_lower for k in ("likee", "x", "twitter", "instagram", "tiktok")) and any(k in name_lower for k in ("متابعين", "followers", "likes", "views", "مشاهدات", "لايكات")))
                        )
                        if is_smm and variant_cost >= Decimal("0.50"):
                            final_price = (final_price / Decimal("1000")).quantize(Decimal("0.00000001"))
                            wholesale_price = (wholesale_price / Decimal("1000")).quantize(Decimal("0.00000001"))
                            vip_price = (vip_price / Decimal("1000")).quantize(Decimal("0.00000001"))
                            variant_cost = (variant_cost / Decimal("1000")).quantize(Decimal("0.00000001"))

                        meta = {
                            "qty_type": qty_type,
                            "qty_min": (qty_min or 1) if qty_type == "range" else 1,
                            "qty_max": (qty_max or 999999) if qty_type == "range" else 1,
                            "qty_list": qty_list,
                            "is_per_mille": is_smm,
                            "product_type": pp.product_type,
                            "remote_id": str(pp.remote_id),
                            "params": [
                                {
                                    "name": param.name,
                                    "label": param.label,
                                    "type": param.parameter_type,
                                    "required": param.required
                                }
                                for param in pp.parameters.all()
                            ] or list(schema_fields.values())
                        }


                        # Clean up naming for TikTok and typos
                        if "tik yok" in variant_name.lower():
                            variant_name = variant_name.replace("Tik Yok", "تيك توك").replace("tik yok", "تيك توك")
                            if "400" in variant_name and "عملة" not in variant_name:
                                variant_name = "تيك توك 400 عملة"
                            elif "150" in variant_name and "عملة" not in variant_name:
                                variant_name = "تيك توك 150 عملة"

                        if ("tik tok" in variant_name.lower() or "تيك توك" in variant_name) and qty_type == "range":
                            if not any(k in variant_name for k in ("400", "150", "متابعين", "لايك", "مشاهدات")):
                                variant_name = "تعبئة رصيد عملات تيك توك (1,000 - 5,000,000)"

                        # Clean up naming and options for Syriatel (سيريتل)
                        v_low = variant_name.lower()
                        sort_num = 0
                        if "syriatel" in v_low or "سيريتل" in v_low or ("fatura" in v_low and "mtn" not in v_low and "turk" not in v_low):
                            if "cash" in v_low or "كاش" in v_low:
                                variant_name = "سيريتل كاش (Syriatel Cash)"
                                sort_num = 3
                                meta["qty_type"] = "range"
                                meta["qty_min"] = 100
                                meta["qty_max"] = 500000
                            elif "fatura" in v_low or "فاتورة" in v_low or "فواتير" in v_low:
                                variant_name = "فواتير سيريتل (Syriatel Fatura)"
                                sort_num = 2
                                meta["qty_type"] = "range"
                                meta["qty_min"] = 100
                                meta["qty_max"] = 5000000
                            elif "credit" in v_low or "رصيد" in v_low or "باقات" in v_low:
                                variant_name = "رصيد وباقات سيريتل (Syriatel Credit)"
                                sort_num = 1
                                meta["qty_type"] = "list"
                                meta["qty_list"] = [
                                    "1000", "2000", "3000", "5000", "10000", "15000", "20000",
                                    "25000", "30000", "50000", "75000", "100000", "150000",
                                    "200000", "250000", "500000", "1000000"
                                ]

                        # Clean up naming and options for MTN (ام تي ان)
                        if "mtn" in v_low or "ام تي ان" in v_low:
                            if "fatura" in v_low or "فاتورة" in v_low or "فواتير" in v_low:
                                variant_name = "فواتير ام تي ان (MTN Fatura)"
                                sort_num = 2
                                meta["qty_type"] = "range"
                                meta["qty_min"] = 100
                                meta["qty_max"] = 5000000
                            elif "credit" in v_low or "رصيد" in v_low or "باقات" in v_low:
                                variant_name = "رصيد وباقات ام تي ان (MTN Credit)"
                                sort_num = 1
                                meta["qty_type"] = "list"
                                if not meta.get("qty_list"):
                                    meta["qty_list"] = [
                                        "1000", "2000", "3000", "5000", "10000", "15000", "20000",
                                        "25000", "30000", "50000", "75000", "100000", "150000",
                                        "200000", "250000", "500000", "1000000"
                                    ]
                            elif "cash" in v_low or "كاش" in v_low:
                                variant_name = "ام تي ان كاش (MTN Cash)"
                                sort_num = 3
                                meta["qty_type"] = "range"
                                meta["qty_min"] = 100
                                meta["qty_max"] = 500000

                        # Determine display sort order
                        if sort_num == 0:
                            if "150" in variant_name:
                                sort_num = 1
                            elif "400" in variant_name:
                                sort_num = 2
                            elif "تعبئة" in variant_name:
                                sort_num = 3
                            elif "رصيد" in variant_name:
                                sort_num = 1
                            elif "فواتير" in variant_name or "فاتورة" in variant_name:
                                sort_num = 2
                            elif "كاش" in variant_name:
                                sort_num = 3

                        # If there is a Level 3 subcategory (e.g. اوتوماتيك 2, يدوي, أمريكي, سعودي, عضويات)
                        # and it is not already in the variant name, append it for clear identification
                        chain = self._get_category_chain(pp)
                        if len(chain) >= 3:
                            subcat_name = chain[2].name.strip()
                            if subcat_name and subcat_name.lower() not in ("null", "none", "default"):
                                if subcat_name.lower() not in variant_name.lower():
                                    variant_name = f"{variant_name} ({subcat_name})"

                        # If multiple items in this product group share the exact same variant_name, append server/option index
                        same_name_items = [x for x in p_items if (x.local_name or x.name or '').strip() == (pp.local_name or pp.name or '').strip()]
                        if len(same_name_items) > 1 and "(سيرفر" not in variant_name:
                            item_idx = same_name_items.index(pp) + 1
                            variant_name = f"{variant_name} (سيرفر {item_idx})"

                        sku_val = f"PRV-{self.profile.id}-{pp.remote_id}"[:80]

                        try:
                            api_pid = int(pp.remote_id)
                        except (ValueError, TypeError):
                            api_pid = None

                        local_variant = ProductVariant.objects.filter(sku=sku_val).first()
                        if not local_variant and api_pid is not None:
                            local_variant = ProductVariant.objects.filter(api_product_id=api_pid, product=local_product).first()

                        variant_is_active = bool(pp.is_active and pp.local_is_active)
                        if variant_cost > Decimal("10000") or remote_id_str == "9486":
                            variant_is_active = False

                        if not local_variant:
                            local_variant = ProductVariant.objects.create(
                                product=local_product,
                                name=variant_name[:120],
                                sku=sku_val,
                                price=final_price,
                                wholesale_price=wholesale_price,
                                vip_price=vip_price,
                                cost=variant_cost,
                                sort_order=sort_num,
                                is_active=variant_is_active,
                                is_temporarily_disabled=not variant_is_active,
                                metadata=meta,
                                api_product_id=api_pid
                            )
                        else:
                            local_variant.product = local_product
                            local_variant.name = variant_name[:120]
                            local_variant.price = final_price
                            local_variant.wholesale_price = wholesale_price
                            local_variant.vip_price = vip_price
                            local_variant.cost = variant_cost
                            if sort_num > 0:
                                local_variant.sort_order = sort_num
                            local_variant.is_active = variant_is_active
                            local_variant.is_temporarily_disabled = not variant_is_active
                            local_variant.metadata = meta
                            if api_pid is not None:
                                local_variant.api_product_id = api_pid
                            local_variant.save()

                        mapping.local_variant = local_variant
                        mapping.save()

            except Exception as e:
                logger.exception("Error mapping group '%s' to catalog: %s", group_name, e)
                continue

        # Clean up any leftover empty products for this provider that have 0 variants
        try:
            Product.objects.filter(
                store=store,
                api_provider=provider_code,
                variants__isnull=True
            ).delete()
        except Exception:
            pass

        # Update is_active and is_out_of_stock on Product models based on active variants
        try:
            from django.db.models import Exists, OuterRef
            active_vars = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)

            # Products with NO active variants -> hide them!
            Product.objects.filter(
                api_provider=provider_code,
                store=store,
            ).annotate(
                has_active=Exists(active_vars)
            ).filter(has_active=False).update(is_active=False, is_out_of_stock=True)

            # Products WITH active variants -> activate them!
            Product.objects.filter(
                api_provider=provider_code,
                store=store,
            ).annotate(
                has_active=Exists(active_vars)
            ).filter(has_active=True).update(is_active=True, is_out_of_stock=False)

            # Sync sub-stores: if platform product is inactive or deleted, sub-store cloned products are also updated
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                inactive_platform_names = list(Product.all_objects.filter(store__isnull=True, is_active=False).values_list("name", flat=True))
                if inactive_platform_names:
                    Product.all_objects.filter(store__isnull=False, name__in=inactive_platform_names).update(is_active=False, is_out_of_stock=True)
                    ProductVariant.all_objects.filter(product__store__isnull=False, product__name__in=inactive_platform_names).update(is_active=False, is_temporarily_disabled=True)
                
                active_platform_names = list(Product.all_objects.filter(store__isnull=True, is_active=True).values_list("name", flat=True))
                if active_platform_names:
                    Product.all_objects.filter(store__isnull=False, name__in=active_platform_names).update(is_active=True, is_out_of_stock=False)
        except Exception as stock_err:
            logger.warning(f"Product availability status sync error: {stock_err}")

        # Clean up empty categories (except standard storefront sections)
        try:
            Category.objects.filter(
                store=store,
                products__isnull=True
            ).exclude(
                name__in=[
                    "شحن الألعاب", "شحن التطبيقات", "اتصالات ورصيد",
                    "بطاقات رقمية", "خدمات التلفزيون والبث", "أرقام وحسابات",
                    "اشتراكات VPN", "الذكاء الاصطناعي", "برامج وتصميم",
                    "تحويلات مالية", "ترويج ودعم السوشيال ميديا"
                ]
            ).delete()
        except Exception:
            pass

    @transaction.atomic
    def map_to_catalog(self, provider_product: ProviderProduct):
        """Creates or updates a Product/Variant in the main store catalog."""
        return self.map_all_to_catalog(ProviderProduct.objects.filter(id=provider_product.id))
