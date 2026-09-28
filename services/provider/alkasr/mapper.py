"""
Canonical Alkasr Catalog & App-Level Hierarchy Mapping Engine.
Mirrors the exact 10-section structure of Alkasr VIP:
- Level 1: 10 Main Sections (قسم الألعاب، قسم الدردشة، قسم الأرصدة، البطاقات، السوشيال ميديا، إلخ)
- Level 2: The Canonical App / Game / Service (Product)
- Level 3: The Packages / Variants (ProductVariants)
Prevents any package from becoming a standalone product and prevents apps from cluttering store categories.
"""

import re
import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

logger = logging.getLogger("provider.alkasr.mapper")

# The 10 Official Alkasr VIP Main Sections
STANDARD_MAIN_SECTIONS = [
    ("قسم الألعاب", 1),
    ("قسم الدردشة والتطبيقات", 2),
    ("قسم الأرصدة والاتصالات", 3),
    ("البطاقات الإلكترونية", 4),
    ("السوشيال ميديا", 5),
    ("خدمات التلفاز والبث", 6),
    ("اشتراكات VPN", 7),
    ("الذكاء الاصطناعي", 8),
    ("برامج وتصميم", 9),
    ("الأرقام والحسابات", 10),
]

# Canonical App & Game Definitions: (Section, Display Name, Matching Keywords)
KNOWN_APPS_REGISTRY = [
    # ── 1. قسم الألعاب ──────────────────────────────────────────────────────────
    ("قسم الألعاب", "ببجي تركيا (PUBG Turkey)", ["pupg turkey", "pubg turkey", "ببجي تركيا"]),
    ("قسم الألعاب", "ببجي موبايل (PUBG Mobile)", ["pubg", "ببجي", "uc", "شدة", "شدات"]),
    ("قسم الألعاب", "فري فاير (Free Fire)", ["free fire", "فري فاير", "ff ", "جواهر"]),
    ("قسم الألعاب", "روبلوكس (Roblox)", ["roblox", "روبلوكس", "robux"]),
    ("قسم الألعاب", "جواكر (Jawaker)", ["jawaker", "جواكر", "توكنز"]),
    ("قسم الألعاب", "كلاش أوف كلانس (Clash of Clans)", ["clash of clans", "كلاش اوف كلانس", "كلاش أوف"]),
    ("قسم الألعاب", "كلاش رويال (Clash Royale)", ["clash royale", "كلاش رويال"]),
    ("قسم الألعاب", "موبايل ليجندز (Mobile Legends)", ["mobile legends", "موبايل ليجند", "موبايل ليجندز"]),
    ("قسم الألعاب", "براول ستارز (Brawl Stars)", ["brawl stars", "براول ستارز"]),
    ("قسم الألعاب", "إي إيه سبورتس إف سي (EA Sports FC)", ["ea sports fc", "ea fc", "fifa", "فيفا"]),
    ("قسم الألعاب", "كول أوف ديوتي موبايل (Call of Duty Mobile)", ["call of duty", "cod mobile", "كول اوف ديوتي"]),
    ("قسم الألعاب", "فالورانت (Valorant)", ["valorant", "فالورانت"]),
    ("قسم الألعاب", "ليغ أوف ليجيندز (League of Legends)", ["league of legends", "lol rp"]),
    ("قسم الألعاب", "أونور أوف كينغز (Honor of Kings)", ["honor of kings"]),

    # ── 2. قسم الدردشة والتطبيقات ──────────────────────────────────────────────
    ("قسم الدردشة والتطبيقات", "يلا لودو (Yalla Ludo)", ["yalla ludo", "يلا لودو"]),
    ("قسم الدردشة والتطبيقات", "بيجو لايف (BIGO LIVE)", ["bigo", "بيجو"]),
    ("قسم الدردشة والتطبيقات", "توب توب (TopTop)", ["toptop", "توب توب"]),
    ("قسم الدردشة والتطبيقات", "لايكي (Likee)", ["likee", "لايكي"]),
    ("قسم الدردشة والتطبيقات", "بوبو لايف (Poppo Live)", ["poppo", "بوبو"]),
    ("قسم الدردشة والتطبيقات", "ميكو لايف (MICO Live)", ["mico", "ميكو"]),
    ("قسم الدردشة والتطبيقات", "إيمو شات (IMO Chat)", ["imo", "إيمو", "ايمو"]),
    ("قسم الدردشة والتطبيقات", "يلا لايف (Yalla Live)", ["yalla live", "يلا لايف"]),
    ("قسم الدردشة والتطبيقات", "ميو لايف (Meyo Live)", ["meyo", "ميو"]),
    ("قسم الدردشة والتطبيقات", "هاي كات (Hi Cat)", ["hi cat", "هاي كات"]),
    ("قسم الدردشة والتطبيقات", "ليف يو (LivU)", ["livu", "ليف يو"]),
    ("قسم الدردشة والتطبيقات", "آزار (Azar Chat)", ["azar", "ازار", "آزار"]),
    ("قسم الدردشة والتطبيقات", "سول ستار (Soul Star)", ["soul star", "سول ستار", "soulstar"]),
    ("قسم الدردشة والتطبيقات", "سول تشيل (SoulChill)", ["soulchill", "soul chill", "سول تشيل", "سوشيل"]),
    ("قسم الدردشة والتطبيقات", "فور فن (4Fun)", ["4fun", "فور فن"]),
    ("قسم الدردشة والتطبيقات", "يويو شات (YoYo Chat)", ["yoyo", "يويو"]),
    ("قسم الدردشة والتطبيقات", "أهلاً شات (Ahlan Chat)", ["ahlan", "اهلا"]),
    ("قسم الدردشة والتطبيقات", "زينة لايف (Xena Live)", ["xena", "زينة لايف"]),
    ("قسم الدردشة والتطبيقات", "هابي شات (Habi Chat)", ["habi", "habby", "هابي"]),
    ("قسم الدردشة والتطبيقات", "أيومي (Ayome)", ["ayome", "ايومي"]),
    ("قسم الدردشة والتطبيقات", "هيا شات (Hiya Chat)", ["hiya", "هيا شات"]),
    ("قسم الدردشة والتطبيقات", "بوبو شات (Bobo Chat)", ["bobo", "بوبو"]),
    ("قسم الدردشة والتطبيقات", "شاميت (Chamet)", ["chamet", "شاميت"]),
    ("قسم الدردشة والتطبيقات", "تانجو لايف (Tango Live)", ["tango live", "تانجو"]),
    ("قسم الدردشة والتطبيقات", "أومي تي في (OmeTV)", ["ometv", "اومي"]),

    # ── 3. قسم الأرصدة والاتصالات ──────────────────────────────────────────────
    ("قسم الأرصدة والاتصالات", "تروكسل تركيا (Turkcell TR)", ["turkcell", "تروكسل"]),
    ("قسم الأرصدة والاتصالات", "ترك تليكوم (Turk Telekom)", ["turk telekom", "ترك تليكوم", "تليكوم"]),
    ("قسم الأرصدة والاتصالات", "فودافون تركيا (Vodafone TR)", ["vodafone", "فودافون"]),
    ("قسم الأرصدة والاتصالات", "سيريتل سوريا (Syriatel)", ["syriatel", "سيريتل"]),
    ("قسم الأرصدة والاتصالات", "إم تي إن سوريا (MTN Syria)", ["mtn", "ام تي ان"]),
    ("قسم الأرصدة والاتصالات", "سلام تليكوم (Selam Telekom)", ["selam", "سلام تليكوم"]),

    # ── 4. البطاقات الإلكترونية ─────────────────────────────────────────────────
    ("البطاقات الإلكترونية", "بطاقات آبل آيتونز (Apple iTunes)", ["itunes", "ايتونز", "آيتونز", "apple"]),
    ("البطاقات الإلكترونية", "بطاقات بلايستيشن (PlayStation Store)", ["playstation", "بلايستيشن", "psn", "ps kuwait", "ps uae", "ps ksa", "ps usa", "ps uk", "ps canada", "ps fransa", "ps oman", "ps qatar", "ps italy", "ps japan"]),
    ("البطاقات الإلكترونية", "بطاقات جوجل بلاي (Google Play)", ["google play", "جوجل بلاي"]),
    ("البطاقات الإلكترونية", "بطاقات روبلوكس (Roblox Cards)", ["roblex", "roblox card", "roblex cards", "roblex usa", "roblex canada", "roblex uae", "كروت روبلوكس", "بطاقات روبلوكس"]),
    ("البطاقات الإلكترونية", "بطاقات ستيم (Steam Wallet)", ["steam", "ستيم"]),
    ("البطاقات الإلكترونية", "بطاقات ريزر جولد (Razer Gold)", ["razer gold", "ريزر جولد", "razer", "ريزر"]),
    ("البطاقات الإلكترونية", "بطاقات فيزا مسبقة الدفع (Visa Cards)", ["visa", "فيزا"]),

    # ── 5. خدمات التلفاز والبث ─────────────────────────────────────────────────
    ("خدمات التلفاز والبث", "نتفلكس (Netflix)", ["netflix", "نتفلكس"]),
    ("خدمات التلفاز والبث", "شاهد VIP (Shahid VIP)", ["shahid", "شاهد"]),
    ("خدمات التلفاز والبث", "زين تي في (Zain TV)", ["zain tv", "زين تي"]),
    ("خدمات التلفاز والبث", "بركات تي في (Barakat TV)", ["barakat tv", "بركات"]),
    ("خدمات التلفاز والبث", "شامنا تي في (Shamna TV)", ["shamna", "شامنا"]),
    ("خدمات التلفاز والبث", "تانجو برو (Tango Pro)", ["tango pro", "تانجو برو"]),

    # ── 6. اشتراكات VPN ────────────────────────────────────────────────────────
    ("اشتراكات VPN", "إكسبريس في بي ان (ExpressVPN)", ["express vpn", "expressvpn"]),
    ("اشتراكات VPN", "نورد في بي ان (NordVPN)", ["nord vpn", "nordvpn"]),
    ("اشتراكات VPN", "بروتون في بي ان (ProtonVPN)", ["proton vpn", "protonvpn"]),
    ("اشتراكات VPN", "سيرف شارك (Surfshark VPN)", ["surfshark"]),
    ("اشتراكات VPN", "لاغو فاست (LagoFast Game Booster)", ["lagofast"]),
    ("اشتراكات VPN", "أدجارد في بي ان (ADguard VPN)", ["adguard"]),
    ("اشتراكات VPN", "سايبر غوست (CyberGhost VPN)", ["cyber ghost", "cyberghost"]),
    ("اشتراكات VPN", "برايفت انترنت اكسس (PIA VPN)", ["pia vpn"]),
    ("اشتراكات VPN", "هوت سبوت شيلد (Hotspot Shield)", ["hotspot"]),
    ("اشتراكات VPN", "تنل بير (TunnelBear VPN)", ["tunnelbear", "tunnelbar"]),
    ("اشتراكات VPN", "ويند سكرايب (Windscribe VPN)", ["windscribe"]),
    ("اشتراكات VPN", "بيور في بي ان (PureVPN)", ["pure vpn", "purevpn"]),
    ("اشتراكات VPN", "آي بي فانيش (IPVanish VPN)", ["ipvanish"]),
    ("اشتراكات VPN", "زوغ في بي ان (Zoog VPN)", ["zoog vpn", "zoog"]),
    ("اشتراكات VPN", "بلانيت في بي ان (Planet VPN)", ["planet vpn"]),
    ("اشتراكات VPN", "بروسك في بي ان (Browsec VPN)", ["browsec"]),
    ("اشتراكات VPN", "أوبن في بي ان (OpenVPN)", ["open vpn", "openvpn"]),

    # ── 7. الذكاء الاصطناعي ───────────────────────────────────────────────────
    ("الذكاء الاصطناعي", "جيميني برو (Gemini Pro AI)", ["gemini", "جيميني"]),
    ("الذكاء الاصطناعي", "بيربلكسيتي برو (Perplexity Pro)", ["perplexity"]),
    ("الذكاء الاصطناعي", "غاما برو (Gamma AI Pro)", ["gamma"]),
    ("الذكاء الاصطناعي", "ليوناردو (Leonardo AI)", ["leonardo"]),

    # ── 8. برامج وتصميم ───────────────────────────────────────────────────────
    ("برامج وتصميم", "كانفا برو (Canva Pro)", ["canva", "كانفا"]),
    ("برامج وتصميم", "بيكس آرت (PicsArt Gold)", ["picsart", "بيكس"]),
    ("برامج وتصميم", "فلات آيكون (Flaticon Access)", ["flaticon"]),

    # ── 9. السوشيال ميديا ──────────────────────────────────────────────────────
    ("السوشيال ميديا", "خدمات تيك توك (TikTok Services)", ["تيك توك", "tiktok"]),
    ("السوشيال ميديا", "خدمات انستغرام (Instagram Services)", ["انستغرام", "instagram"]),
    ("السوشيال ميديا", "خدمات فيسبوك (Facebook Services)", ["فيس بوك", "فيسبوك", "facebook"]),
    ("السوشيال ميديا", "خدمات إكس تويتر (Twitter / X Services)", ["تويتر", "twitter", " x "]),
    ("السوشيال ميديا", "خدمات يوتيوب (YouTube Services)", ["يوتيوب", "youtube"]),
]


class AlkasrMapperService:
    """
    App-Level Canonical Mapper for Alkasr VIP Provider Catalog.
    
    Architecture:
    1. Categories are STRICTLY the 10 Standard Main Sections.
    2. Products represent the Game / App / Service (e.g. PUBG Mobile, Free Fire, Canva Pro).
    3. ProductVariants represent the Packages (e.g. 60 UC, 325 UC, 1 Month) linked to that Product.
    """

    def __init__(self, profile):
        self.profile = profile
        self.store = getattr(profile, "store", None)
        self._categories_cache = {}

    def _ensure_standard_sections(self):
        """Pre-creates the 10 standard categories in catalog.Category."""
        from apps.catalog.models import Category

        for name, order in STANDARD_MAIN_SECTIONS:
            cat = Category.objects.filter(store=self.store, name=name).first()
            if not cat:
                cat = Category.objects.create(
                    store=self.store,
                    name=name,
                    sort_order=order,
                    is_active=True
                )
            elif cat.sort_order != order:
                cat.sort_order = order
                cat.save(update_fields=["sort_order", "updated_at"])
            self._categories_cache[name] = cat

    def _get_catalog_category(self, section_name: str):
        """Gets category from cache or database."""
        from apps.catalog.models import Category

        if section_name in self._categories_cache:
            return self._categories_cache[section_name]

        cat = Category.objects.filter(store=self.store, name=section_name).first()
        if not cat:
            cat = Category.objects.create(
                store=self.store,
                name=section_name,
                is_active=True
            )
        self._categories_cache[section_name] = cat
        return cat

    def resolve_app_and_section(self, pp) -> Tuple[str, str]:
        """
        Determines the Main Section and App/Game name for a ProviderProduct.
        Returns: (section_name, app_name)
        """
        from apps.providers.models import ProviderProduct

        # Gather all contextual names: product name, local name, category names, ancestor category names, and parent product names
        names_to_check = []
        if pp.name:
            names_to_check.append(pp.name)
        if pp.local_name:
            names_to_check.append(pp.local_name)
        if pp.provider_category_name:
            names_to_check.append(pp.provider_category_name)

        curr_cat = pp.category
        cat_ancestors = []
        while curr_cat:
            if curr_cat.name:
                cat_ancestors.append(curr_cat.name)
                names_to_check.append(curr_cat.name)
            curr_cat = curr_cat.parent

        if pp.remote_parent_id and str(pp.remote_parent_id) not in ("0", ""):
            parent_pp = ProviderProduct.objects.filter(
                profile=self.profile,
                remote_id=str(pp.remote_parent_id)
            ).first()
            if parent_pp:
                if parent_pp.name:
                    names_to_check.append(parent_pp.name)
                if parent_pp.local_name:
                    names_to_check.append(parent_pp.local_name)
                if parent_pp.provider_category_name:
                    names_to_check.append(parent_pp.provider_category_name)
                p_cat = parent_pp.category
                while p_cat:
                    if p_cat.name:
                        cat_ancestors.append(p_cat.name)
                        names_to_check.append(p_cat.name)
                    p_cat = p_cat.parent

        combined = " ".join(names_to_check).lower()

        # 0. Check Dynamic Admin Rules (ProviderAppRule)
        try:
            from apps.providers.models import ProviderAppRule
            admin_rules = ProviderAppRule.objects.filter(is_active=True).order_by("-priority")
            for rule in admin_rules:
                if rule.keyword and rule.keyword.strip().lower() in combined:
                    return rule.section, rule.app_name
        except Exception:
            pass

        # 1. SPECIAL CASE: ROBLOX / ROBLEX Gift Cards vs In-Game
        if any(w in combined for w in ("roblox", "roblex", "robux", "روبلوكس", "روبلكس")):
            if any(w in combined for w in ("card", "cards", "كارت", "كروت", "بطاق", "usa", "canada", "uae", "$", "dollar", "دولار")) or any("بطاق" in a.lower() for a in cat_ancestors):
                return "البطاقات الإلكترونية", "بطاقات روبلوكس (Roblox Cards)"
            else:
                return "قسم الألعاب", "روبلوكس (Roblox)"

        # 2. Match from Known Registry
        for section, app_name, keywords in KNOWN_APPS_REGISTRY:
            if any(kw.lower() in combined for kw in keywords):
                return section, app_name

        # 3. Check for intermediate/server names to skip
        # e.g. "سيرفر 1", "تومتيك", "يدوي" should NOT be app names
        GENERIC_TIER_WORDS = (
            "سيرفر", "server", "تومتيك", "يدوي", "اوتوماتيك", "باقة", "package", 
            "tier", "شحن الألعاب", "الألعاب", "شحن", "قسم الألعاب", "قسم الدردشة",
            "قسم الأرصدة", "البطاقات الالكترونية", "السوشيال ميديا (خدمات )",
            "خدمات التلفاز", "الأرقام والحسابات", "الذكاء الاصطناعي", "قسم التصميم",
            "اشتراكات vpn"
        )
        candidate_app = ""
        for name in cat_ancestors:
            clean_n = name.strip()
            if not any(w in clean_n.lower() for w in GENERIC_TIER_WORDS) and len(clean_n) > 2:
                candidate_app = clean_n
                break

        if not candidate_app:
            candidate_app = pp.provider_category_name or (pp.category.name if pp.category else "") or pp.name or "خدمة عامة"
            if any(w in candidate_app.lower() for w in GENERIC_TIER_WORDS):
                if pp.remote_parent_id and str(pp.remote_parent_id) not in ("0", ""):
                    parent_pp = ProviderProduct.objects.filter(profile=self.profile, remote_id=str(pp.remote_parent_id)).first()
                    if parent_pp and parent_pp.name:
                        candidate_app = parent_pp.name

        # 4. STRICT HEURISTIC CLASSIFICATION (Specific services evaluated first, NO "شحن" in games!)
        # Social Media Services (Check first to avoid any leakage!)
        if any(k in combined for k in ("تيك توك", "tiktok", "انستغرام", "انستقرام", "instagram", "فيسبوك", "فيس بوك", "facebook", "تويتر", "twitter", " x ", "يوتيوب", "youtube", "تيليجرام", "تليجرام", "telegram", "متابعين", "لايكات", "مشاهدات", "سوشيال", "social")):
            return "السوشيال ميديا", candidate_app

        # Telecom & Balance
        if any(k in combined for k in ("تروكسل", "turkcell", "تليكوم", "telekom", "فودافون", "vodafone", "سيريتل", "syriatel", "mtn", "رصيد", "ليرات", "فواتير", "باقات شهرية", "باقات اسبوعية")):
            return "قسم الأرصدة والاتصالات", candidate_app

        # Gift Cards
        if any(k in combined for k in ("بطاقة", "بطاقات", "كارت", "كروت", "card", "gift", "itunes", "playstation", "psn", "google play", "steam", "razer")):
            return "البطاقات الإلكترونية", candidate_app

        # VPN
        if any(k in combined for k in ("vpn", "بروكسي", "proxy")):
            return "اشتراكات VPN", candidate_app

        # TV & Streaming
        if any(k in combined for k in ("نتفلكس", "netflix", "شاهد", "shahid", "iptv", "تلفاز", "tv", "بث")):
            return "خدمات التلفاز والبث", candidate_app

        # AI Tools
        if any(k in combined for k in ("ذكاء", "ai", "gemini", "chatgpt", "gpt", "perplexity", "gamma", "leonardo")):
            return "الذكاء الاصطناعي", candidate_app

        # Software & Design
        if any(k in combined for k in ("تصميم", "كانفا", "canva", "picsart", "flaticon", "فوتوشوب", "برامج")):
            return "برامج وتصميم", candidate_app

        # Numbers & Accounts
        if any(k in combined for k in ("أرقام", "ارقام", "حسابات", "number", "account")):
            return "الأرقام والحسابات", candidate_app

        # Chat & Live Applications
        if any(k in combined for k in ("دردشة", "شات", "chat", "live", "لايف", "بيجو", "لايكي", "بوبو", "ميكو", "ماسات", "كوينز")):
            return "قسم الدردشة والتطبيقات", candidate_app

        # Games (Strict: Only confirmed games, NEVER arbitrary services or diamonds!)
        if any(k in combined for k in ("pubg", "ببجي", "free fire", "فري فاير", "jawaker", "جواكر", "roblox", "روبلوكس", "ألعاب", "games", "لعبة")):
            if not any(k in combined for k in ("سوشيال", "social", "دردشة", "chat", "لايف", "live", "فولو", "متابعين", "لايكات", "مشاهدات", "كارت", "بطاق", "card")):
                return "قسم الألعاب", candidate_app

        # Default fallback is Chat & Applications, NEVER games!
        return "قسم الدردشة والتطبيقات", candidate_app

    @staticmethod
    def build_form_schema(raw_params: list, app_name: str) -> dict:
        """Constructs catalog form_schema from provider parameters list with smart fallback."""
        fields = []
        seen_names = set()

        if isinstance(raw_params, list):
            for idx, p in enumerate(raw_params):
                if isinstance(p, dict):
                    name = str(p.get("name") or p.get("key") or f"param_{idx}").strip()
                    label = str(p.get("label") or p.get("name") or name).strip()
                    p_type = str(p.get("type") or "text").strip()
                    required = bool(p.get("required", True))
                elif isinstance(p, str):
                    clean_str = p.strip()
                    name = "playerId" if idx == 0 else f"param_{idx}"
                    label = clean_str or "معرف الحساب"
                    p_type = "text"
                    required = True
                else:
                    continue

                if name and name not in seen_names:
                    seen_names.add(name)
                    fields.append({
                        "name": name,
                        "label": label,
                        "type": p_type,
                        "required": required
                    })

        # Fallback if provider didn't send explicit params
        if not fields:
            app_lower = app_name.lower()
            if any(k in app_lower for k in ("ببجي", "pubg", "free fire", "فري فاير", "roblox", "روبلوكس", "jawaker", "جواكر", "لعبة", "game")):
                fields.append({"name": "playerId", "label": "معرف اللاعب (Player ID)", "type": "text", "required": True})
            elif any(k in app_lower for k in ("سيريتل", "syriatel", "mtn", "تروكسل", "turkcell", "اتصالات", "رصيد")):
                fields.append({"name": "phone_number", "label": "رقم الهاتف / الحساب", "type": "text", "required": True})
            elif any(k in app_lower for k in ("تيك توك", "انستغرام", "سوشيال", "متابعين", "لايكات")):
                fields.append({"name": "link", "label": "رابط الحساب أو المنشور", "type": "url", "required": True})
            else:
                fields.append({"name": "playerId", "label": "معرف الحساب (User ID)", "type": "text", "required": True})

        return {"version": 1, "fields": fields}

    def map_all_to_catalog(self, selected_group_names=None) -> Dict[str, int]:
        """
        Groups all ProviderProducts under their Canonical Apps (Products)
        and attaches each ProviderProduct as a ProductVariant.
        """
        from apps.providers.models import ProviderProduct, ProviderMapping, ProviderPrice
        from apps.catalog.models import Product, ProductVariant

        provider_code = "alkasr"
        self._ensure_standard_sections()

        products_qs = ProviderProduct.objects.filter(profile=self.profile)

        stats = {
            "root_products_created": 0,
            "root_products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "disabled_count": 0,
        }

        # 1. Group ProviderProducts by (Section, App Name)
        grouped_by_app: Dict[Tuple[str, str], List[ProviderProduct]] = {}

        for pp in products_qs:
            section_name, app_name = self.resolve_app_and_section(pp)
            key = (section_name, app_name)
            grouped_by_app.setdefault(key, []).append(pp)

        # 2. Create or Update Products and map their Variants
        for (section_name, app_name), pp_list in grouped_by_app.items():
            with transaction.atomic():
                catalog_cat = self._get_catalog_category(section_name)

                # Look up existing Product by (store, category, name)
                local_product = Product.objects.filter(
                    store=self.store,
                    category=catalog_cat,
                    name=app_name[:160]
                ).first()

                # Collect all parameters across all variants for this app
                combined_params = []
                for p_item in pp_list:
                    if p_item.raw_params:
                        combined_params.extend(p_item.raw_params)

                schema = self.build_form_schema(combined_params, app_name)

                # Check if any variant has a category image
                img_url = ""
                for p_item in pp_list:
                    if p_item.provider_category_img:
                        img_url = p_item.provider_category_img
                        break

                meta = dict(local_product.metadata or {}) if local_product else {}
                if img_url:
                    meta["image_url"] = img_url

                # Primary provider ID (first item's parent_id or id)
                first_pp = pp_list[0]
                primary_pid = None
                try:
                    raw_p = first_pp.remote_parent_id or first_pp.remote_id
                    primary_pid = int(raw_p) if raw_p else None
                except (ValueError, TypeError):
                    primary_pid = None

                if not local_product:
                    local_product = Product.objects.create(
                        store=self.store,
                        name=app_name[:160],
                        category=catalog_cat,
                        is_active=True,
                        is_out_of_stock=False,
                        track_inventory=False,
                        quantity=999999,
                        is_api_product=True,
                        api_provider=provider_code,
                        api_product_id=primary_pid,
                        provider_parent_id=0,
                        form_schema=schema,
                        metadata=meta
                    )
                    stats["root_products_created"] += 1
                else:
                    local_product.category = catalog_cat
                    local_product.is_api_product = True
                    local_product.api_provider = provider_code
                    if primary_pid and not local_product.api_product_id:
                        local_product.api_product_id = primary_pid
                    local_product.form_schema = schema
                    local_product.metadata = meta
                    local_product.save()
                    stats["root_products_updated"] += 1

                # Identify container items that act as parents to other items in this app
                parent_remote_ids = set()
                for p_item in pp_list:
                    if p_item.remote_parent_id and str(p_item.remote_parent_id) not in ("0", ""):
                        parent_remote_ids.add(str(p_item.remote_parent_id))

                # 3. Create or Update ProductVariants inside this Product
                for pp in pp_list:
                    try:
                        pkg_pid = int(pp.remote_id)
                    except (ValueError, TypeError):
                        continue

                    # If this provider product acts as a parent container to other items and has 0 cost, skip variant creation
                    if str(pkg_pid) in parent_remote_ids and pp.cost_price == 0:
                        ProviderMapping.objects.update_or_create(
                            provider_product=pp,
                            defaults={
                                "local_product": local_product,
                                "local_variant": None
                            }
                        )
                        continue

                    # Pricing
                    pricing = getattr(pp, "pricing", None)
                    cost = pp.cost_price
                    final_price = pricing.final_price if pricing else cost
                    wholesale_price = pricing.final_wholesale_price if pricing else cost
                    vip_price = pricing.final_vip_price if pricing else cost

                    # Quantity type
                    if pp.product_type == "fixed_quantities" or (pp.qty_list and len(pp.qty_list) > 0):
                        qty_type = "list"
                    elif pp.product_type == "amount" or (pp.qty_min and pp.qty_max and pp.qty_max > pp.qty_min and pp.qty_max > 1):
                        qty_type = "range"
                    else:
                        qty_type = "fixed"

                    sku_val = f"PRV-{self.profile.id}-{pkg_pid}"[:80]
                    is_active = bool(pp.is_active and pp.local_is_active)
                    raw_v_name = (pp.local_name or pp.name or f"باقة {pkg_pid}").strip()
                    cat_hint = (pp.provider_category_name or (pp.category.name if pp.category else "") or "").strip()
                    
                    # Normalize Arabic to detect generic section names
                    clean_hint = cat_hint.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").lower()
                    is_generic = any(g in clean_hint for g in ("قسم", "شحن", "العاب", "دردشة", "ارصدة", "بطاقات", "سوشيال", "تلفاز", "خدمات", "services", "category"))

                    if cat_hint and not is_generic and cat_hint.lower() not in raw_v_name.lower() and cat_hint.lower() not in app_name.lower():
                        v_name = f"{raw_v_name} ({cat_hint})"[:120]
                    else:
                        v_name = raw_v_name[:120]

                    v_meta = {
                        "qty_type": qty_type,
                        "qty_min": pp.qty_min or 1,
                        "qty_max": pp.qty_max or 999999,
                        "qty_list": pp.qty_list or [],
                        "product_type": pp.product_type,
                        "remote_id": str(pkg_pid),
                        "parent_id": str(pp.remote_parent_id or ""),
                        "params": pp.raw_params or []
                    }

                    local_variant = ProductVariant.objects.filter(sku=sku_val).first()
                    if not local_variant:
                        local_variant = ProductVariant.objects.filter(
                            product=local_product,
                            api_product_id=pkg_pid
                        ).first()

                    parent_id_int = None
                    try:
                        parent_id_int = int(pp.remote_parent_id) if pp.remote_parent_id else None
                    except (ValueError, TypeError):
                        parent_id_int = None

                    if not local_variant:
                        local_variant = ProductVariant.objects.create(
                            product=local_product,
                            name=v_name,
                            sku=sku_val,
                            price=final_price,
                            wholesale_price=wholesale_price,
                            vip_price=vip_price,
                            cost=cost,
                            is_active=is_active,
                            is_temporarily_disabled=not is_active,
                            api_product_id=pkg_pid,
                            provider_parent_id=parent_id_int,
                            metadata=v_meta
                        )
                        stats["variants_created"] += 1
                    else:
                        local_variant.product = local_product
                        local_variant.name = v_name
                        local_variant.price = final_price
                        local_variant.wholesale_price = wholesale_price
                        local_variant.vip_price = vip_price
                        local_variant.cost = cost
                        local_variant.is_active = is_active
                        local_variant.is_temporarily_disabled = not is_active
                        local_variant.api_product_id = pkg_pid
                        local_variant.provider_parent_id = parent_id_int
                        local_variant.metadata = v_meta
                        local_variant.save()
                        stats["variants_updated"] += 1

                    # Update ProviderMapping
                    ProviderMapping.objects.update_or_create(
                        provider_product=pp,
                        defaults={
                            "local_product": local_product,
                            "local_variant": local_variant
                        }
                    )

        # 4. Soft-disable Stale Variants & Products
        with transaction.atomic():
            active_provider_pids = set()
            for p in products_qs.filter(is_active=True):
                try:
                    active_provider_pids.add(int(p.remote_id))
                except (ValueError, TypeError):
                    pass

            stale_variants = ProductVariant.objects.filter(
                sku__startswith=f"PRV-{self.profile.id}-"
            ).exclude(api_product_id__in=active_provider_pids)

            disabled_cnt = stale_variants.filter(is_active=True).update(
                is_active=False,
                is_temporarily_disabled=True
            )
            stats["disabled_count"] += disabled_cnt

            active_vars = ProductVariant.objects.filter(
                product=OuterRef("pk"),
                is_active=True,
                is_temporarily_disabled=False
            )

            # Products with active variants -> active
            Product.objects.filter(
                store=self.store,
                api_provider=provider_code
            ).annotate(has_active=Exists(active_vars)).filter(has_active=True).update(
                is_active=True,
                is_out_of_stock=False
            )

            # Products with NO active variants -> inactive & out of stock
            Product.objects.filter(
                store=self.store,
                api_provider=provider_code
            ).annotate(has_active=Exists(active_vars)).filter(has_active=False).update(
                is_active=False,
                is_out_of_stock=True
            )

        # 5. Clean up Obsolete / Standalone Package Products & Orphaned Alkasr Products
        with transaction.atomic():
            from apps.orders.models import OrderItem
            from apps.catalog.models import Category
            
            canonical_names = set(app_name[:160] for (_, app_name) in grouped_by_app.keys())
            
            # Find any product associated with this provider whose name is NOT in canonical_names
            # e.g. "ROBLOX 10$", "ROBLOX 25$", "ROBLOX 50$", "ROBLOX", "سيرفر 1", "تومتيك", etc.
            obsolete_candidates = Product.objects.filter(
                Q(api_provider=provider_code) |
                Q(variants__sku__startswith=f"PRV-{self.profile.id}-") |
                Q(name__in=["ROBLOX 10$", "ROBLOX 25$", "ROBLOX 50$", "ROBLOX", "Tik tok"]),
                store=self.store
            ).exclude(name__in=canonical_names).distinct()

            deleted_prods_cnt = 0
            deactivated_prods_cnt = 0
            for old_p in obsolete_candidates:
                has_orders = OrderItem.objects.filter(variant__product=old_p).exists()
                if not has_orders:
                    old_p.variants.all().delete()
                    old_p.delete()
                    deleted_prods_cnt += 1
                else:
                    old_p.is_active = False
                    old_p.is_out_of_stock = True
                    old_p.variants.all().update(is_active=False, is_temporarily_disabled=True)
                    old_p.save(update_fields=["is_active", "is_out_of_stock"])
                    deactivated_prods_cnt += 1

            stats["obsolete_products_deleted"] = deleted_prods_cnt
            stats["obsolete_products_deactivated"] = deactivated_prods_cnt

            # Clean empty non-standard categories
            std_cat_names = [name for name, _ in STANDARD_MAIN_SECTIONS]
            Category.objects.filter(
                store=self.store,
                products__isnull=True
            ).exclude(name__in=std_cat_names).delete()

        return stats

    @classmethod
    def cleanup_corrupted_mappings(cls, profile=None) -> Dict[str, int]:
        """
        Database cleanup routine (PHASE 6).
        Identifies and repairs misassigned packages across the catalog:
        1. Fixes variants where variant.product.api_product_id != variant.provider_parent_id.
        2. Deactivates synthetic / orphaned variants.
        """
        from apps.catalog.models import Product, ProductVariant

        reassigned_count = 0
        deactivated_count = 0

        qs = ProductVariant.objects.filter(
            provider_parent_id__isnull=False,
            provider_parent_id__gt=0
        ).select_related("product")

        if profile:
            qs = qs.filter(sku__startswith=f"PRV-{profile.id}-")

        with transaction.atomic():
            for v in qs:
                # If variant parent does not match Product.api_product_id
                if not v.product or v.product.api_product_id != v.provider_parent_id:
                    correct_parent = Product.objects.filter(
                        api_provider="alkasr",
                        api_product_id=v.provider_parent_id
                    ).first()

                    if correct_parent:
                        v.product = correct_parent
                        v.save(update_fields=["product", "updated_at"])
                        reassigned_count += 1
                    else:
                        v.is_active = False
                        v.is_temporarily_disabled = True
                        v.save(update_fields=["is_active", "is_temporarily_disabled", "updated_at"])
                        deactivated_count += 1

        logger.info(
            "Cleanup completed: %d variants reassigned to correct parent, %d orphaned variants deactivated.",
            reassigned_count, deactivated_count
        )
        return {
            "reassigned_count": reassigned_count,
            "deactivated_count": deactivated_count
        }
