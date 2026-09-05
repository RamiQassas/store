import logging
from decimal import Decimal
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant, Category

logger = logging.getLogger(__name__)

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
        """
        Determines the parent Product name (Application / Service / Brand),
        e.g. ببجي موبايل (PUBG Global), فري فاير (Free Fire), سيريتل (Syriatel), نتفلكس (Netflix).
        """
        generic_names = {
            "null", "none", "games", "live application", "data and communication", 
            "gift cards", "tv services", "money transfers", "social media", 
            "numbers and accounts", "program activation numbers", "ألعاب", "عام",
            "شحن الألعاب", "شحن التطبيقات", "رصيد الهاتف", "تفعيل الأرقام المؤقتة",
            "ترويج ودعم السوشيال ميديا", "بطاقات الهدايا", "العملات الرقمية", "default",
            "قسم الألعاب", "قسم الدردشة", "قسم الأرصدة", "قسم الأرصدة والاتصالات",
            "البطاقات الالكترونية", "البطاقات الإلكترونية", "خدمات التلفاز", "الأرقام والحسابات",
            "الذكاء الاصطناعي", "قسم التصميم", "اشتراكات vpn"
        }

        # Subcategories & Server names mapped to parent Application
        subcat_to_app = {
            # PUBG Subcategories / Servers
            "اوتوماتيك 2": "ببجي موبايل (PUBG Global)",
            "اوتوماتيك 3": "ببجي موبايل (PUBG Global)",
            "يدوي ٢": "ببجي موبايل (PUBG Global)",
            "يدوي 2": "ببجي موبايل (PUBG Global)",
            "يدوي": "ببجي موبايل (PUBG Global)",
            "برايم": "ببجي موبايل (PUBG Global)",
            "برايم بلس": "ببجي موبايل (PUBG Global)",
            "بطاقة نخبة": "ببجي موبايل (PUBG Global)",
            "الحزم": "ببجي موبايل (PUBG Global)",
            "آلي 2": "ببجي موبايل (PUBG Global)",
            "سيرفر 3": "ببجي موبايل (PUBG Global)",
            "سيرفر 4": "ببجي موبايل (PUBG Global)",
            "سيرفر 6": "ببجي موبايل (PUBG Global)",
            "سيرفر 7": "ببجي موبايل (PUBG Global)",
            "سيرفر 8": "ببجي موبايل (PUBG Global)",
            "سيرفر 9": "ببجي موبايل (PUBG Global)",
            "سيرفر 10": "ببجي موبايل (PUBG Global)",
            "سيرفر 11": "ببجي موبايل (PUBG Global)",
            "سيرفر 12": "ببجي موبايل (PUBG Global)",
            "سيرفر 17": "ببجي موبايل (PUBG Global)",
            "سيرفر 18": "ببجي موبايل (PUBG Global)",
            "prime": "ببجي موبايل (PUBG Global)",
            "prime +": "ببجي موبايل (PUBG Global)",
            "pubg tr": "ببجي موبايل تركيا (PUBG TR)",
            "ببجي تركي يدوي": "ببجي موبايل تركيا (PUBG TR)",

            # Turkcell Subcategories
            "aylık paketler": "تروكسل تركيا (Turkcell)",
            "aylık teklifler": "تروكسل تركيا (Turkcell)",
            "haftalık paketler": "تروكسل تركيا (Turkcell)",
            "günlük paketler": "تروكسل تركيا (Turkcell)",
            "nar paketler": "تروكسل تركيا (Turkcell)",
            "uluslararası paketler": "تروكسل تركيا (Turkcell)",
            "internet wi̇-fi̇": "باقات إنترنت واي فاي (Wi-Fi)",
            "internet wi-fi": "باقات إنترنت واي فاي (Wi-Fi)",

            # PlayStation Subcategories / Regions
            "ps usa": "بطاقات بلايستيشن (PlayStation)",
            "ps ksa": "بطاقات بلايستيشن (PlayStation)",
            "ps uae": "بطاقات بلايستيشن (PlayStation)",
            "ps uk": "بطاقات بلايستيشن (PlayStation)",
            "ps canada": "بطاقات بلايستيشن (PlayStation)",
            "ps fransa": "بطاقات بلايستيشن (PlayStation)",
            "ps germany": "بطاقات بلايستيشن (PlayStation)",
            "ps italy": "بطاقات بلايستيشن (PlayStation)",
            "ps japan": "بطاقات بلايستيشن (PlayStation)",
            "ps oman": "بطاقات بلايستيشن (PlayStation)",
            "ps qatar": "بطاقات بلايستيشن (PlayStation)",

            # Steam Subcategories
            "steam global": "بطاقات ستيم (Steam)",
            "steam turkey": "بطاقات ستيم (Steam)",

            # Razer Gold Subcategories
            "razer gold global": "بطاقات ريزر جولد (Razer Gold)",
            "razer turkey": "بطاقات ريزر جولد (Razer Gold)",

            # Google Play Subcategories
            "google play usa": "بطاقات جوجل بلاي (Google Play)",
            "google play turkey": "بطاقات جوجل بلاي (Google Play)",

            # iTunes Subcategories
            "itunes usa": "بطاقات أبل / آيتونز (iTunes)",
            "itunes turkey": "بطاقات أبل / آيتونز (iTunes)",

            # Roblox Cards
            "roblex usa": "بطاقات روبلوكس (Roblox Cards)",

            # Streaming / TV
            "+disney": "ديزني بلس (Disney+)",
            "+osn": "او اس ان بلس (OSN+)",
            "blue 4k": "بلو فور كي (BLUE 4K IPTV)",

            # Apps / Chat
            "ludo diamonds": "يلا لودو (Yalla Ludo)",
            "tik tok": "تيك توك (TikTok)",
            "mixu ميكس يو": "ميكس يو (Mixu)",
            "party star": "بارتي ستار (Party Star)",
            "soul accessoris": "سول (Soul App)",
            "star lite": "ستار لايت (Star Lite)",
            "tango pro": "تانجو برو (Tango Pro)",
            "tumile": "تومي (Tumile)",
            "yaahlan": "يهلا (Yaahlan)",
            "zepeto zems": "زيبيتو (Zepeto)",
            "zepito coins": "زيبيتو (Zepeto)",
            "bermuda": "برمودا (Bermuda Chat)",
            "weplay gold": "وي بلاي (WePlay)",
            "هاي كات": "هاي كات (Hi Cat)",

            # VPN
            "hotspot shield": "اشتراكات Hotspot Shield",
            "lagofast booster": "اشتراكات LagoFast",

            # Software / Social
            "auto reply for facebook": "رد تلقائي فيسبوك (Facebook Auto Reply)",
            "auto reply for what's app": "رد تلقائي واتساب (WhatsApp Auto Reply)",
            "auto reply for instagram": "رد تلقائي انستغرام (Instagram Auto Reply)",
            "خدماات يوتيوب": "خدمات يوتيوب (YouTube)",
            "قسم التلجرام": "تفعيل أرقام تليجرام (Telegram)",
            "ready accounts": "حسابات جاهزة (Ready Accounts)",
            "1370": "سناب شات بلس (Snapchat Plus)",
            "1332": "ببجي موبايل (PUBG Global)",
            "1350": "تفعيل أرقام واتساب (WhatsApp)",
            "snapchat": "سناب شات بلس (Snapchat Plus)",
            "سناب شات": "سناب شات بلس (Snapchat Plus)",
            "سناب شات بلس": "سناب شات بلس (Snapchat Plus)",
        }

        app_name_map = {
            # Games
            "PUBG GLOBAL ببجي عالمية": "ببجي موبايل (PUBG Global)",
            "Pupg Turkey ببجي تركيا": "ببجي موبايل تركيا (PUBG TR)",
            "FREE FIRE GLOBAL": "فري فاير (Free Fire)",
            "ROBLOX": "روبلوكس (Roblox)",
            "Jawaker جواكر": "جواكر (Jawaker)",
            
            # Live & Chat Apps
            "IMO CHAT": "إيمو شات (IMO Chat)",
            "LIVU": "ليف يو (LivU)",
            "MEYO LIVE": "ميو لايف (Meyo Live)",
            "YALLA LIVE": "يلا لايف (Yalla Live)",
            "YALLA LUDO": "يلا لودو (Yalla Ludo)",
            "AZAR CHAT": "أزار شات (Azar Chat)",
            "بارتي ستار": "بارتي ستار (Party Star)",
            "Yaahlan": "يهلا (Yaahlan)",
            "Hi Cat": "هاي كات (Hi Cat)",
            "TIKTOK": "تيك توك (TikTok)",
            "BIGO LIVE": "بيجو لايف (Bigo Live)",
            "LIKEE": "لايكي (Likee)",

            # Telecom / Balance
            "Syriatell": "سيريتل كاش ورصيد (Syriatel)",
            "MTN سوريا": "ام تي ان كاش ورصيد (MTN)",
            "تروكسل Turkcell": "تروكسل تركيا (Turkcell)",
            "ترك تليكوم Türk Telekom": "ترك تليكوم تركيا (Türk Telekom)",
            "فودافون Vodafone": "فودافون تركيا (Vodafone)",
            "Selam Telekom": "سلام تليكوم (Selam)",

            # Cards
            "ITUNES": "بطاقات أبل / آيتونز (iTunes)",
            "PLAYSTATION CARDS": "بطاقات بلايستيشن (PlayStation)",
            "GOOGLE PLAY": "بطاقات جوجل بلاي (Google Play)",
            "STEAM": "بطاقات ستيم (Steam)",
            "RAZER GOLD": "بطاقات ريزر جولد (Razer Gold)",
            "ROBLEX Cards": "بطاقات روبلوكس (Roblox Cards)",
            "Visa Cards": "بطاقات فيزا (Visa Cards)",

            # TV & Streaming
            "NETFLIX": "نتفلكس (Netflix)",
            "SHAHID": "شاهد VIP (Shahid VIP)",
            "شامنا SHAMNA": "شامنا تي في (Shamna TV)",
            "Zain TV": "زين تي في (Zain TV)",
            "BARAKAT TV": "بركات تي في (Barakat TV)",
            "TANGO PRO": "تانجو برو (Tango Pro)",

            # Accounts & Numbers
            "قسم الواتساب": "تفعيل أرقام واتساب (WhatsApp)",
            "GeMini Pro": "جيميني برو (Gemini Pro AI)",
            "Picsart": "بيكس آرت (Picsart)",
        }

        # Check remote category ID directly from subcat_to_app
        cat_remote = str(getattr(pp.category, 'remote_id', '') or '').strip()
        cat_parent_remote = str(getattr(pp.category, 'parent_remote_id', '') or '').strip()
        if cat_remote in subcat_to_app:
            return subcat_to_app[cat_remote]
        if cat_parent_remote in subcat_to_app:
            return subcat_to_app[cat_parent_remote]

        # Guard against pure duration names like "3 شهور" becoming application names
        import re
        if re.match(r'^\d+\s*(شهر|شهور|سنة|سنوات|أيام|يوم|day|days|month|months|year|years)$', (pp.name or '').strip(), re.IGNORECASE):
            if cat_remote in ("1370", "null") or (pp.category and pp.category.parent and "social" in (pp.category.parent.name or '').lower()):
                return "سناب شات بلس (Snapchat Plus)"
            chain = self._get_category_chain(pp)
            if chain and len(chain) >= 2 and chain[1].name.strip().lower() not in generic_names:
                return chain[1].name.strip()
            cat_raw_name = (pp.category.name if pp.category else "").strip()
            if cat_raw_name and cat_raw_name.lower() not in generic_names:
                return cat_raw_name
            return "سناب شات بلس (Snapchat Plus)"

        # 1. Check parent category from ProviderCategory relation
        if pp.category and pp.category.parent:
            p_name = pp.category.parent.name.strip()
            if p_name in app_name_map:
                return app_name_map[p_name]
            if p_name.lower() in subcat_to_app:
                return subcat_to_app[p_name.lower()]
            if p_name.lower() not in generic_names and len(p_name) >= 3:
                return p_name

        # 2. Check category chain (Level 1: App/Game)
        chain = self._get_category_chain(pp)
        if len(chain) >= 2:
            raw_app = chain[1].name.strip()
            if raw_app in app_name_map:
                return app_name_map[raw_app]
            if raw_app.lower() in subcat_to_app:
                return subcat_to_app[raw_app.lower()]
            if raw_app.lower() not in generic_names:
                return raw_app

        # 3. Check current category against subcat_to_app
        cat_raw = (pp.category.name if pp.category else "").strip()
        if cat_raw:
            if cat_raw in app_name_map:
                return app_name_map[cat_raw]
            if cat_raw.lower() in subcat_to_app:
                return subcat_to_app[cat_raw.lower()]

        # 4. Keyword matching from product name
        prod_name = (pp.name or "").strip()
        p_low = prod_name.lower()

        # Games
        if "pubg" in p_low or "ببجي" in prod_name or "uc" in p_low:
            if "turkey" in p_low or "تركيا" in prod_name:
                return "ببجي موبايل تركيا (PUBG TR)"
            return "ببجي موبايل (PUBG Global)"
        if "free fire" in p_low or "فري فاير" in prod_name:
            return "فري فاير (Free Fire)"
        if "roblox" in p_low or "روبلوكس" in prod_name:
            return "روبلوكس (Roblox)"
        if "jawaker" in p_low or "جواكر" in prod_name:
            return "جواكر (Jawaker)"
        if "mobile legends" in p_low or "موبايل ليجند" in prod_name:
            return "موبايل ليجندز (Mobile Legends)"
        if "call of duty" in p_low or "كول اوف ديوتي" in prod_name or "كود موبايل" in prod_name:
            return "كول أوف ديوتي (Call of Duty)"
        if "valorant" in p_low or "فالورانت" in prod_name:
            return "فالورانت (Valorant)"
        if "fortnite" in p_low or "فورتنايت" in prod_name or "فورت نايت" in prod_name:
            return "فورت نايت (Fortnite)"
        if "clash of clans" in p_low or "كلاش" in prod_name:
            return "كلاش أوف كلانس (Clash of Clans)"

        # Apps
        if "tiktok" in p_low or "تيك توك" in prod_name:
            return "تيك توك (TikTok)"
        if "yalla" in p_low or "يلا" in prod_name:
            return "يلا لودو (Yalla Ludo)"
        if "bigo" in p_low or "بيجو" in prod_name:
            return "بيجو لايف (Bigo Live)"
        if "likee" in p_low or "لايكي" in prod_name:
            return "لايكي (Likee)"
        if "shahid" in p_low or "شاهد" in prod_name:
            return "شاهد VIP (Shahid VIP)"
        if "netflix" in p_low or "نتفلكس" in prod_name:
            return "نتفلكس (Netflix)"

        # Cards
        if "google play" in p_low or "جوجل بلاي" in prod_name:
            return "بطاقات جوجل بلاي (Google Play)"
        if "itunes" in p_low or "apple" in p_low or "ايتونز" in prod_name or "ابل" in prod_name:
            return "بطاقات أبل / آيتونز (iTunes)"
        if "playstation" in p_low or "psn" in p_low or "بلايستيشن" in prod_name or p_low.startswith("ps "):
            return "بطاقات بلايستيشن (PlayStation)"
        if "xbox" in p_low or "اكس بوكس" in prod_name:
            return "بطاقات إكس بوكس (Xbox)"
        if "steam" in p_low or "ستيم" in prod_name:
            return "بطاقات ستيم (Steam)"
        if "razer" in p_low or "ريزر" in prod_name:
            return "بطاقات ريزر جولد (Razer Gold)"

        # Telecom
        if "syriatel" in p_low or "سيريتل" in prod_name:
            return "سيريتل كاش ورصيد (Syriatel)"
        if "mtn" in p_low or "ام تي ان" in prod_name:
            return "ام تي ان كاش ورصيد (MTN)"
        if "turkcell" in p_low or "تروكسل" in prod_name or "kolay paket" in p_low:
            return "تروكسل تركيا (Turkcell)"

        import re
        clean_name = re.sub(r'[\d\+\$].*', '', prod_name).strip()
        clean_name = re.sub(r'(\s*-\s*|\s*_\s*)$', '', clean_name).strip()
        if len(clean_name) >= 3 and clean_name.lower() not in generic_names:
            return clean_name

        if cat_raw and cat_raw.lower() not in generic_names:
            return cat_raw

        return prod_name or "خدمة عامة"

    def _get_store_category(self, pp, store):
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

        chain = self._get_category_chain(pp)
        root_name = (chain[0].name or "").strip().lower() if chain else ""

        section_map = {
            "قسم الألعاب": "شحن الألعاب",
            "games": "شحن الألعاب",
            "ألعاب": "شحن الألعاب",
            "قسم الدردشة": "شحن التطبيقات",
            "live application": "شحن التطبيقات",
            "تطبيقات": "شحن التطبيقات",
            "شحن التطبيقات": "شحن التطبيقات",
            "قسم الأرصدة": "اتصالات ورصيد",
            "قسم الأرصدة والاتصالات": "اتصالات ورصيد",
            "data and communication": "اتصالات ورصيد",
            "اتصالات ورصيد": "اتصالات ورصيد",
            "رصيد الهاتف": "اتصالات ورصيد",
            "البطاقات الالكترونية": "بطاقات رقمية",
            "البطاقات الإلكترونية": "بطاقات رقمية",
            "gift cards": "بطاقات رقمية",
            "بطاقات رقمية": "بطاقات رقمية",
            "خدمات التلفاز": "خدمات التلفزيون والبث",
            "خدمات التلفاز والـ iptv": "خدمات التلفزيون والبث",
            "tv services": "خدمات التلفزيون والبث",
            "خدمات التلفزيون والبث": "خدمات التلفزيون والبث",
            "الأرقام والحسابات": "أرقام وحسابات",
            "numbers and accounts": "أرقام وحسابات",
            "program activation numbers": "أرقام وحسابات",
            "أرقام وحسابات": "أرقام وحسابات",
            "اشتراكات vpn": "اشتراكات VPN",
            "vpn": "اشتراكات VPN",
            "الذكاء الاصطناعي": "الذكاء الاصطناعي",
            "قسم التصميم": "برامج وتصميم",
            "money transfers": "تحويلات مالية",
            "social media": "ترويج ودعم السوشيال ميديا",
        }

        target_name = section_map.get(root_name)

        # Infer strictly from group_name and product keywords if not determined by root
        if not target_name:
            g_name = self._get_group_name(pp)
            p_low = f"{g_name} {pp.name or ''} {root_name}".lower()

            if any(k in p_low for k in ("pubg", "ببجي", "free fire", "فري فاير", "roblox", "روبلوكس", "game", "العاب", "ألعاب", "jawaker", "جواكر", "clash", "valorant", "fortnite", "mobile legends", "call of duty", "uc", "شدات", "ماسات", "diamond", "weplay")):
                target_name = "شحن الألعاب"
            elif any(k in p_low for k in ("tiktok", "تيك توك", "yalla", "يلا", "bigo", "بيجو", "likee", "لايكي", "imo", "إيمو", "azar", "أزار", "livu", "ليف يو", "meyo", "ميو", "party star", "soul", "star lite", "tumile", "yaahlan", "hi cat", "bermuda", "zepeto", "chat", "شات", "دردشة", "live", "لايف", "mixu")):
                target_name = "شحن التطبيقات"
            elif any(k in p_low for k in ("turkcell", "تروكسل", "telekom", "تليكوم", "vodafone", "فودافون", "syriatel", "سيريتل", "mtn", "رصيد", "fatura", "فاتورة", "باقات", "paket", "wi-fi", "واي فاي")):
                target_name = "اتصالات ورصيد"
            elif any(k in p_low for k in ("playstation", "بلايستيشن", "psn", "itunes", "ايتونز", "آيتونز", "apple", "ابل", "أبل", "google play", "جوجل", "steam", "ستيم", "razer", "ريزر", "بطاقات", "cards", "card", "فيزا", "visa", "voucher")):
                target_name = "بطاقات رقمية"
            elif any(k in p_low for k in ("netflix", "نتفلكس", "نتفليكس", "shahid", "شاهد", "shamna", "شامنا", "tv", "تلفاز", "تلفزيون", "disney", "ديزني", "osn", "او اس ان", "blue 4k", "iptv", "tango pro", "زين تي في", "بركات")):
                target_name = "خدمات التلفزيون والبث"
            elif any(k in p_low for k in ("whatsapp", "واتساب", "telegram", "تلغرام", "تليجرام", "رقم", "أرقام", "ارقام", "number", "accounts", "حسابات جاهزة")):
                target_name = "أرقام وحسابات"
            elif any(k in p_low for k in ("vpn", "بروكسي", "proxy", "hotspot", "lagofast", "expressvpn", "nordvpn")):
                target_name = "اشتراكات VPN"
            elif any(k in p_low for k in ("gemini", "جيميني", "gpt", "chatgpt", "ذكاء", "ai")):
                target_name = "الذكاء الاصطناعي"
            elif any(k in p_low for k in ("picsart", "بيكس آرت", "canva", "كانفا", "رد تلقائي", "auto reply", "تصميم", "برامج")):
                target_name = "برامج وتصميم"
            elif any(k in p_low for k in ("حوالات", "تحويلات", "money transfer")):
                target_name = "تحويلات مالية"
            elif any(k in p_low for k in ("يوتيوب", "youtube", "سوشيال ميديا", "social media")):
                target_name = "ترويج ودعم السوشيال ميديا"
            else:
                target_name = "شحن الألعاب"

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
            ProviderProduct.objects.filter(profile=self.profile).update(is_active=True, local_is_active=True)
            products_qs = ProviderProduct.objects.filter(profile=self.profile, local_is_active=True)

        # Clean up any dot/placeholder products from previous runs
        Product.objects.filter(api_provider="tafa3olcard", name__regex=r'^[\.\s\-_=~*#]+$').delete()
        ProviderProduct.objects.filter(profile=self.profile, name__regex=r'^[\.\s\-_=~*#]+$').delete()

        # Deactivate any variants whose provider product is disabled or deleted
        try:
            inactive_remote_ids = list(ProviderProduct.objects.filter(profile=self.profile, local_is_active=False).values_list('remote_id', flat=True))
            if inactive_remote_ids:
                ProductVariant.objects.filter(api_product_id__in=[int(x) for x in inactive_remote_ids if str(x).isdigit()]).update(is_active=False, is_temporarily_disabled=True)
        except Exception:
            pass
            
        products_list = list(products_qs.select_related('category', 'category__parent', 'pricing').prefetch_related('parameters'))
        store = self.profile.store
        if not store:
            from apps.stores.models import Store
            store = Store.objects.first()
            if store and not self.profile.store:
                try:
                    self.profile.store = store
                    self.profile.save(update_fields=['store'])
                except Exception:
                    pass

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

            if selected_group_names and group_name not in selected_group_names:
                continue
            grouped_products.setdefault(group_name, []).append(pp)

        for group_name, p_items in grouped_products.items():
            try:
                with transaction.atomic():
                    # Find or create store category for this group
                    store_category = self._get_store_category(p_items[0], store)

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

                    # Map each ProviderProduct as a ProductVariant (باقة) inside this single Product
                    for pp in p_items:
                        mapping = ProviderMapping.objects.filter(provider_product=pp).first()
                        if not mapping:
                            mapping = ProviderMapping(provider_product=pp)

                        mapping.local_product = local_product

                        pricing = getattr(pp, 'pricing', None)
                        final_price = pricing.final_price if pricing else pp.cost_price
                        wholesale_price = pricing.final_wholesale_price if pricing else pp.cost_price
                        vip_price = pricing.final_vip_price if pricing else pp.cost_price

                        # Determine quantity type, min, max, list, and per-mille flag
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

                        qty_list = getattr(pp, 'qty_list', None) or []

                        # Fixed amount package detection: when min == max and min > 1 (e.g. TikTok 400 coins, TikTok 150 coins)
                        is_fixed_amount_package = (
                            qty_min is not None and qty_max is not None and qty_min == qty_max and qty_min > 1
                        )

                        if qty_list and len(qty_list) > 0:
                            qty_type = "list"
                        elif is_fixed_amount_package:
                            qty_type = "fixed"
                        elif qty_max is not None and qty_min is not None and qty_max > qty_min:
                            qty_type = "range"
                        elif pp.product_type == "amount" and qty_max is not None and qty_min is not None and qty_max > qty_min:
                            qty_type = "range"
                        elif pp.product_type == "amount" and (qty_min is None or qty_max is None):
                            qty_type = "range"
                        elif pp.product_type in ("fixed_quantities", "specificPackage"):
                            qty_type = "list"
                        else:
                            qty_type = "fixed"

                        variant_cost = pp.cost_price
                        if is_fixed_amount_package:
                            multiplier = Decimal(str(qty_min))
                            final_price = final_price * multiplier
                            wholesale_price = wholesale_price * multiplier
                            vip_price = vip_price * multiplier
                            variant_cost = variant_cost * multiplier

                        is_per_mille = False
                        if not is_fixed_amount_package:
                            if qty_min is not None and qty_min >= 100:
                                is_per_mille = True
                            elif pp.product_type == "amount" and (qty_min is None or qty_min >= 10):
                                is_per_mille = True

                        meta = {
                            "qty_type": qty_type,
                            "qty_min": 1 if is_fixed_amount_package else (qty_min or 1),
                            "qty_max": 1 if is_fixed_amount_package else (qty_max or 999999),
                            "package_qty": qty_min if is_fixed_amount_package else None,
                            "qty_list": qty_list,
                            "is_per_mille": is_per_mille,
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
                            ]
                        }

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
                                # Skip corrupted/un-named variant
                                continue

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

                        # Determine display sort order
                        sort_num = 0
                        if "150" in variant_name:
                            sort_num = 1
                        elif "400" in variant_name:
                            sort_num = 2
                        elif "تعبئة" in variant_name:
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
