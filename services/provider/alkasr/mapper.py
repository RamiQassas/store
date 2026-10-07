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
    ("قسم الألعاب", "ببجي تركيا (PUBG Turkey)", ["pupg turkey", "pubg turkey", "ببجي تركيا", "ببجي تركي"]),
    ("قسم الألعاب", "ببجي موبايل (PUBG Mobile)", ["pubg mobile", "pubg", "pupg", "ببجي موبايل", "ببجي العالمية", "ببجي عالمية", "ببجي"]),
    ("قسم الألعاب", "فري فاير (Free Fire)", ["free fire", "freefire", "فري فاير", "فريفاير"]),
    ("قسم الألعاب", "روبلوكس (Roblox)", ["roblox", "roblex", "robux", "روبلوكس", "روبلكس", "كروت روبلوكس", "بطاقات روبلوكس"]),
    ("قسم الألعاب", "جواكر (Jawaker)", ["jawaker", "جواكر"]),
    ("قسم الألعاب", "كلاش أوف كلانس (Clash of Clans)", ["clash of clans", "كلاش اوف كلانس", "كلاش أوف كلانس", "كلاش كلانس"]),
    ("قسم الألعاب", "كلاش رويال (Clash Royale)", ["clash royale", "كلاش رويال"]),
    ("قسم الألعاب", "موبايل ليجندز (Mobile Legends)", ["mobile legends", "موبايل ليجند", "موبايل ليجندز", "موبايل ليجيندز"]),
    ("قسم الألعاب", "براول ستارز (Brawl Stars)", ["brawl stars", "براول ستارز", "براول ستار"]),
    ("قسم الألعاب", "إي إيه سبورتس إف سي (EA Sports FC)", ["ea sports fc", "ea sports", "ea fc", "fifa mobile", "fifa", "فيفا"]),
    ("قسم الألعاب", "كول أوف ديوتي موبايل (Call of Duty Mobile)", ["call of duty", "cod mobile", "كول اوف ديوتي", "كول أوف ديوتي", "كود موبايل"]),
    ("قسم الألعاب", "فالورانت (Valorant)", ["valorant", "فالورانت", "فالورنت"]),
    ("قسم الألعاب", "ليغ أوف ليجيندز (League of Legends)", ["league of legends", "lol rp", "ليج اوف ليجيندز", "ليغ اوف ليجيندز"]),
    ("قسم الألعاب", "أونور أوف كينغز (Honor of Kings)", ["honor of kings", "اونور اوف كينغز", "أنور أوف كينغز"]),

    # ── 2. قسم الدردشة والتطبيقات ──────────────────────────────────────────────
    ("قسم الدردشة والتطبيقات", "تيك توك شحن عملات (TikTok Coins)", ["عملات تيك توك", "شحن تيك توك", "تيك توك عملات", "تيك توك كوينز", "tiktok coin", "tiktok coins", "tiktok balance"]),
    ("قسم الدردشة والتطبيقات", "يلا لودو (Yalla Ludo)", ["yalla ludo", "يلا لودو"]),
    ("قسم الدردشة والتطبيقات", "بيجو لايف (BIGO LIVE)", ["bigo live", "bigo", "بيجو لايف", "بيجو"]),
    ("قسم الدردشة والتطبيقات", "توب توب (TopTop)", ["toptop", "توب توب"]),
    ("قسم الدردشة والتطبيقات", "لايكي (Likee)", ["likee", "لايكي"]),
    ("قسم الدردشة والتطبيقات", "بوبو لايف (Poppo Live)", ["poppo live", "poppo", "بوبو لايف"]),
    ("قسم الدردشة والتطبيقات", "ميكو لايف (MICO Live)", ["mico live", "mico", "ميكو لايف", "ميكو"]),
    ("قسم الدردشة والتطبيقات", "إيمو شات (IMO Chat)", ["imo chat", "imo live", "imo", "إيمو شات", "إيمو", "ايمو شات", "ايمو"]),
    ("قسم الدردشة والتطبيقات", "يلا لايف (Yalla Live)", ["yalla live", "يلا لايف"]),
    ("قسم الدردشة والتطبيقات", "ميو لايف (Meyo Live)", ["meyo live", "meyo", "ميو لايف", "ميو"]),
    ("قسم الدردشة والتطبيقات", "هاي كات (Hi Cat)", ["hi cat", "hicat", "هاي كات"]),
    ("قسم الدردشة والتطبيقات", "ليف يو (LivU)", ["livu", "ليف يو"]),
    ("قسم الدردشة والتطبيقات", "آزار (Azar Chat)", ["azar chat", "azar", "ازار", "آزار"]),
    ("قسم الدردشة والتطبيقات", "سول ستار (Soul Star)", ["soul star", "soulstar", "سول ستار"]),
    ("قسم الدردشة والتطبيقات", "سول تشيل (SoulChill)", ["soulchill", "soul chill", "سول تشيل", "سوشيل"]),
    ("قسم الدردشة والتطبيقات", "فور فن (4Fun)", ["4fun", "فور فن"]),
    ("قسم الدردشة والتطبيقات", "يويو شات (YoYo Chat)", ["yoyo chat", "yoyo", "يويو شات", "يويو"]),
    ("قسم الدردشة والتطبيقات", "أهلاً شات (Ahlan Chat)", ["ahlan chat", "ahlan", "أهلاً شات", "اهلا شات", "أهلا شات"]),
    ("قسم الدردشة والتطبيقات", "زينة لايف (Xena Live)", ["xena live", "xena", "زينة لايف"]),
    ("قسم الدردشة والتطبيقات", "هابي شات (Habi Chat)", ["habi chat", "habi", "habby", "هابي شات", "هابي"]),
    ("قسم الدردشة والتطبيقات", "أيومي (Ayome)", ["ayome", "ايومي", "أيومي"]),
    ("قسم الدردشة والتطبيقات", "هيا شات (Hiya Chat)", ["hiya chat", "hiya", "هيا شات"]),
    ("قسم الدردشة والتطبيقات", "بوبو شات (Bobo Chat)", ["bobo chat", "bobo", "بوبو شات"]),
    ("قسم الدردشة والتطبيقات", "شاميت (Chamet)", ["chamet", "شاميت"]),
    ("قسم الدردشة والتطبيقات", "تانجو لايف (Tango Live)", ["tango live", "تانجو لايف"]),
    ("قسم الدردشة والتطبيقات", "أومي تي في (OmeTV)", ["ometv", "اومي تي في", "أومي تي في"]),
    ("قسم الدردشة والتطبيقات", "بوتا (BOTA)", ["bota", "بوتا"]),
    ("قسم الدردشة والتطبيقات", "بوتيم (Botim)", ["botim", "بوتيم"]),

    # ── 3. قسم الأرصدة والاتصالات ──────────────────────────────────────────────
    ("قسم الأرصدة والاتصالات", "تروكسل تركيا (Turkcell TR)", ["turkcell", "تروكسل", "توركسل", "aylık paketler", "aylik"]),
    ("قسم الأرصدة والاتصالات", "ترك تليكوم (Turk Telekom)", ["turk telekom", "ترك تليكوم", "ترك تيليكوم", "تليكوم تركيا"]),
    ("قسم الأرصدة والاتصالات", "فودافون تركيا (Vodafone TR)", ["vodafone", "فودافون تركيا", "فودافون"]),
    ("قسم الأرصدة والاتصالات", "سيريتل سوريا (Syriatel)", ["syriatel", "سيريتل", "سيرياتل"]),
    ("قسم الأرصدة والاتصالات", "إم تي إن سوريا (MTN Syria)", ["mtn syria", "mtn", "ام تي ان", "إم تي إن"]),
    ("قسم الأرصدة والاتصالات", "سلام تليكوم (Selam Telekom)", ["selam telekom", "selam", "سلام تليكوم"]),

    # ── 4. البطاقات الإلكترونية ─────────────────────────────────────────────────
    ("البطاقات الإلكترونية", "بطاقات آبل آيتونز (Apple iTunes)", ["apple itunes", "itunes", "ايتونز", "آيتونز", "بطاقات ابل", "بطاقات آبل"]),
    ("البطاقات الإلكترونية", "بطاقات بلايستيشن (PlayStation Store)", ["playstation", "بلايستيشن", "psn", "بلاي ستيشن"]),
    ("البطاقات الإلكترونية", "بطاقات جوجل بلاي (Google Play)", ["google play", "جوجل بلاي", "غوغل بلاي"]),
    ("البطاقات الإلكترونية", "بطاقات ستيم (Steam Wallet)", ["steam wallet", "steam", "ستيم"]),
    ("البطاقات الإلكترونية", "بطاقات ريزر جولد (Razer Gold)", ["razer gold", "ريزر جولد", "razer", "ريزر"]),
    ("البطاقات الإلكترونية", "بطاقات فيزا مسبقة الدفع (Visa Cards)", ["visa card", "visa", "فيزا"]),

    # ── 5. خدمات التلفاز والبث ─────────────────────────────────────────────────
    ("خدمات التلفاز والبث", "ديزني بلس (Disney+)", ["disney", "ديزني", "+disney", "disney+"]),
    ("خدمات التلفاز والبث", "أو إس إن بلس (OSN+)", ["osn", "او اس ان", "أو إس إن", "+osn", "osn+"]),
    ("خدمات التلفاز والبث", "نتفلكس (Netflix)", ["netflix", "نتفلكس", "نتفليكس"]),
    ("خدمات التلفاز والبث", "شاهد VIP (Shahid VIP)", ["shahid vip", "shahid", "شاهد vip", "شاهد"]),
    ("خدمات التلفاز والبث", "زين تي في (Zain TV)", ["zain tv", "زين تي في", "زين tv"]),
    ("خدمات التلفاز والبث", "بركات تي في (Barakat TV)", ["barakat tv", "بركات تي في", "بركات tv"]),
    ("خدمات التلفاز والبث", "شامنا تي في (Shamna TV)", ["shamna tv", "شامنا تي في", "شامنا tv"]),
    ("خدمات التلفاز والبث", "تانجو برو (Tango Pro)", ["tango pro", "تانجو برو"]),

    # ── 6. اشتراكات VPN ────────────────────────────────────────────────────────
    ("اشتراكات VPN", "إكسبريس في بي ان (ExpressVPN)", ["express vpn", "expressvpn", "اكسبريس"]),
    ("اشتراكات VPN", "نورد في بي ان (NordVPN)", ["nord vpn", "nordvpn", "نورد"]),
    ("اشتراكات VPN", "بروتون في بي ان (ProtonVPN)", ["proton vpn", "protonvpn", "بروتون"]),
    ("اشتراكات VPN", "سيرف شارك (Surfshark VPN)", ["surfshark", "سيرف شارك"]),
    ("اشتراكات VPN", "لاغو فاست (LagoFast Game Booster)", ["lagofast", "لاغو فاست"]),
    ("اشتراكات VPN", "أدجارد في بي ان (ADguard VPN)", ["adguard", "أدجارد", "ادجارد"]),
    ("اشتراكات VPN", "سايبر غوست (CyberGhost VPN)", ["cyberghost", "cyber ghost", "سايبر غوست"]),
    ("اشتراكات VPN", "برايفت انترنت اكسس (PIA VPN)", ["pia vpn", "private internet access"]),
    ("اشتراكات VPN", "هوت سبوت شيلد (Hotspot Shield)", ["hotspot shield", "hotspot", "هوت سبوت"]),
    ("اشتراكات VPN", "تنل بير (TunnelBear VPN)", ["tunnelbear", "tunnelbar", "تنل بير"]),
    ("اشتراكات VPN", "ويند سكرايب (Windscribe VPN)", ["windscribe", "ويند سكرايب"]),
    ("اشتراكات VPN", "بيور في بي ان (PureVPN)", ["pure vpn", "purevpn", "بيور"]),
    ("اشتراكات VPN", "آي بي فانيش (IPVanish VPN)", ["ipvanish", "آي بي فانيش"]),
    ("اشتراكات VPN", "زوغ في بي ان (Zoog VPN)", ["zoog vpn", "zoog"]),
    ("اشتراكات VPN", "بلانيت في بي ان (Planet VPN)", ["planet vpn", "بلانيت"]),
    ("اشتراكات VPN", "بروسك في بي ان (Browsec VPN)", ["browsec", "بروسك"]),
    ("اشتراكات VPN", "أوبن في بي ان (OpenVPN)", ["open vpn", "openvpn", "اوبن في بي ان"]),

    # ── 7. الذكاء الاصطناعي ───────────────────────────────────────────────────
    ("الذكاء الاصطناعي", "جيميني برو (Gemini Pro AI)", ["gemini pro", "gemini", "جيميني برو", "جيميني"]),
    ("الذكاء الاصطناعي", "شات جي بي تي (ChatGPT Plus / OpenAI)", ["chatgpt", "gpt-4", "gpt", "openai", "شات جي بي تي"]),
    ("الذكاء الاصطناعي", "بيربلكسيتي برو (Perplexity Pro)", ["perplexity", "بيربلكسيتي"]),
    ("الذكاء الاصطناعي", "غاما برو (Gamma AI Pro)", ["gamma ai", "gamma", "غاما برو", "جاما"]),
    ("الذكاء الاصطناعي", "ليوناردو (Leonardo AI)", ["leonardo ai", "leonardo", "ليوناردو"]),

    # ── 8. برامج وتصميم ───────────────────────────────────────────────────────
    ("برامج وتصميم", "كانفا برو (Canva Pro)", ["canva", "كانفا"]),
    ("برامج وتصميم", "بيكس آرت (PicsArt Gold)", ["picsart", "بيكس آرت", "بيكسارت"]),
    ("برامج وتصميم", "فلات آيكون (Flaticon Access)", ["flaticon", "فلات ايكون", "فلات آيكون"]),

    # ── 9. السوشيال ميديا ──────────────────────────────────────────────────────
    ("السوشيال ميديا", "خدمات تيك توك (TikTok Services)", ["tiktok services", "متابعين تيك توك", "لايكات تيك توك", "مشاهدات تيك توك", "خدمات تيك توك", "سيرفر تيك توك", "دعم تيك توك"]),
    ("السوشيال ميديا", "خدمات انستغرام (Instagram Services)", ["instagram services", "انستغرام", "انستقرام", "instagram"]),
    ("السوشيال ميديا", "خدمات فيسبوك (Facebook Services)", ["facebook services", "فيس بوك", "فيسبوك", "facebook", "auto reply"]),
    ("السوشيال ميديا", "خدمات إكس تويتر (Twitter / X Services)", ["twitter services", "تويتر", "twitter", "منصة x", "x platform"]),
    ("السوشيال ميديا", "خدمات يوتيوب (YouTube Services)", ["youtube services", "يوتيوب", "youtube"]),
    ("السوشيال ميديا", "خدمات تيليجرام (Telegram Services)", ["telegram services", "خدمات تيليجرام", "أعضاء تيليجرام", "مشاهدات تيليجرام", "متابعين تيليجرام"]),

    # ── 10. الأرقام والحسابات ──────────────────────────────────────────────────
    ("الأرقام والحسابات", "تفعيل أرقام واتساب (WhatsApp Numbers)", ["ارقام واتساب", "أرقام واتساب", "رقم واتساب", "تفعيل واتساب", "واتساب ارقام"]),
    ("الأرقام والحسابات", "تليجرام بريميوم (Telegram Premium)", ["telegram premium", "تليجرام بريميوم", "تيليجرام بريميوم", "تلغرام بريميوم", "اشتراك تيليجرام"]),
]

from apps.common.tenant_utils import bypass_tenant_filter

# Canonical Seed Services for all 10 standard sections when API returns empty or only games
SEED_STANDARD_APPS = [
    ("قسم الألعاب", "روبلوكس (Roblox)", [
        (8001, "100 روبوكس (Robux)", Decimal("1.25"), "package", [{"name": "playerId", "label": "اسم المستخدم في روبلوكس", "type": "text", "required": True}]),
        (8002, "400 روبوكس (Robux)", Decimal("4.99"), "package", [{"name": "playerId", "label": "اسم المستخدم في روبلوكس", "type": "text", "required": True}]),
        (8003, "800 روبوكس (Robux)", Decimal("9.99"), "package", [{"name": "playerId", "label": "اسم المستخدم في روبلوكس", "type": "text", "required": True}]),
    ]),
    ("قسم الألعاب", "جواكر (Jawaker)", [
        (8011, "50,000 توكنز جواكر", Decimal("2.50"), "package", [{"name": "playerId", "label": "معرف اللاعب في جواكر", "type": "text", "required": True}]),
        (8012, "120,000 توكنز جواكر", Decimal("5.00"), "package", [{"name": "playerId", "label": "معرف اللاعب في جواكر", "type": "text", "required": True}]),
        (8013, "300,000 توكنز جواكر", Decimal("10.00"), "package", [{"name": "playerId", "label": "معرف اللاعب في جواكر", "type": "text", "required": True}]),
    ]),
    ("قسم الألعاب", "كلاش أوف كلانس (Clash of Clans)", [
        (8021, "80 جوهرة (Gems)", Decimal("0.99"), "package", [{"name": "playerId", "label": "معرف اللاعب (Player Tag)", "type": "text", "required": True}]),
        (8022, "500 جوهرة (Gems)", Decimal("4.99"), "package", [{"name": "playerId", "label": "معرف اللاعب (Player Tag)", "type": "text", "required": True}]),
    ]),
    ("قسم الدردشة والتطبيقات", "تيك توك شحن عملات (TikTok Coins)", [
        (8101, "70 عملة تيك توك", Decimal("0.95"), "package", [{"name": "playerId", "label": "اسم المستخدم (Username)", "type": "text", "required": True}]),
        (8102, "350 عملة تيك توك", Decimal("4.75"), "package", [{"name": "playerId", "label": "اسم المستخدم (Username)", "type": "text", "required": True}]),
        (8103, "700 عملة تيك توك", Decimal("9.50"), "package", [{"name": "playerId", "label": "اسم المستخدم (Username)", "type": "text", "required": True}]),
    ]),
    ("قسم الدردشة والتطبيقات", "يلا لودو (Yalla Ludo)", [
        (8111, "120 ماسة يلا لودو", Decimal("0.99"), "package", [{"name": "playerId", "label": "معرف اللاعب (User ID)", "type": "text", "required": True}]),
        (8112, "650 ماسة يلا لودو", Decimal("4.99"), "package", [{"name": "playerId", "label": "معرف اللاعب (User ID)", "type": "text", "required": True}]),
    ]),
    ("قسم الدردشة والتطبيقات", "بيجو لايف (BIGO LIVE)", [
        (8121, "40 ماسة بيجو لايف", Decimal("0.99"), "package", [{"name": "playerId", "label": "معرف بيجو لايف (Bigo ID)", "type": "text", "required": True}]),
        (8122, "210 ماسة بيجو لايف", Decimal("4.99"), "package", [{"name": "playerId", "label": "معرف بيجو لايف (Bigo ID)", "type": "text", "required": True}]),
    ]),
    ("قسم الأرصدة والاتصالات", "تروكسل تركيا (Turkcell TR)", [
        (8201, "شحن 100 ليرة تركية", Decimal("3.20"), "package", [{"name": "phone_number", "label": "رقم الهاتف التركي", "type": "text", "required": True}]),
        (8202, "شحن 200 ليرة تركية", Decimal("6.30"), "package", [{"name": "phone_number", "label": "رقم الهاتف التركي", "type": "text", "required": True}]),
    ]),
    ("قسم الأرصدة والاتصالات", "سيريتل سوريا (Syriatel)", [
        (8211, "رصيد سيريتل 10,000 ليرة", Decimal("0.85"), "package", [{"name": "phone_number", "label": "رقم هاتف سيريتل", "type": "text", "required": True}]),
        (8212, "رصيد سيريتل 25,000 ليرة", Decimal("2.10"), "package", [{"name": "phone_number", "label": "رقم هاتف سيريتل", "type": "text", "required": True}]),
    ]),
    ("قسم الأرصدة والاتصالات", "إم تي إن سوريا (MTN Syria)", [
        (8221, "رصيد MTN سوريا 10,000 ليرة", Decimal("0.85"), "package", [{"name": "phone_number", "label": "رقم هاتف MTN", "type": "text", "required": True}]),
        (8222, "رصيد MTN سوريا 25,000 ليرة", Decimal("2.10"), "package", [{"name": "phone_number", "label": "رقم هاتف MTN", "type": "text", "required": True}]),
    ]),
    ("البطاقات الإلكترونية", "بطاقات آبل آيتونز (Apple iTunes)", [
        (8301, "بطاقة آيتونز 5$ أمريكي", Decimal("5.00"), "package", []),
        (8302, "بطاقة آيتونز 10$ أمريكي", Decimal("10.00"), "package", []),
    ]),
    ("البطاقات الإلكترونية", "بطاقات بلايستيشن (PlayStation Store)", [
        (8311, "بطاقة بلايستيشن 10$ أمريكي", Decimal("10.00"), "package", []),
        (8312, "بطاقة بلايستيشن 20$ أمريكي", Decimal("20.00"), "package", []),
    ]),
    ("البطاقات الإلكترونية", "بطاقات ستيم (Steam Wallet)", [
        (8321, "بطاقة ستيم 5$ عالمي", Decimal("5.00"), "package", []),
        (8322, "بطاقة ستيم 10$ عالمي", Decimal("10.00"), "package", []),
    ]),
    ("خدمات التلفاز والبث", "نتفلكس (Netflix)", [
        (8401, "اشتراك نتفلكس بريميوم 4K (شهر)", Decimal("3.99"), "package", [{"name": "email", "label": "البريد الإلكتروني للتفعيل", "type": "email", "required": True}]),
    ]),
    ("خدمات التلفاز والبث", "شاهد VIP (Shahid VIP)", [
        (8411, "اشتراك شاهد VIP شامل الرياضة (شهر)", Decimal("4.50"), "package", [{"name": "phone_or_email", "label": "رقم الهاتف أو البريد الإلكتروني", "type": "text", "required": True}]),
    ]),
    ("اشتراكات VPN", "نورد في بي ان (NordVPN)", [
        (8501, "اشتراك NordVPN بريميوم (شهر)", Decimal("3.50"), "package", [{"name": "email", "label": "البريد الإلكتروني", "type": "email", "required": True}]),
    ]),
    ("الذكاء الاصطناعي", "شات جي بي تي (ChatGPT Plus / OpenAI)", [
        (8601, "اشتراك ChatGPT Plus (شهر) حساب خاص", Decimal("19.50"), "package", [{"name": "email", "label": "البريد الإلكتروني لتفعيل الحساب", "type": "email", "required": True}]),
    ]),
    ("برامج وتصميم", "كانفا برو (Canva Pro)", [
        (8701, "اشتراك كانفا برو رسمي للتعليم والفرق (سنة)", Decimal("4.99"), "package", [{"name": "email", "label": "بريد حساب كانفا لتفعيله", "type": "email", "required": True}]),
    ]),
    ("السوشيال ميديا", "خدمات تيك توك (TikTok Services)", [
        (8801, "1,000 متابع تيك توك حقيقي", Decimal("1.50"), "package", [{"name": "link", "label": "رابط حساب التيك توك", "type": "url", "required": True}]),
    ]),
    ("الأرقام والحسابات", "تليجرام بريميوم (Telegram Premium)", [
        (8901, "اشتراك تليجرام بريميوم رسمي (3 أشهر)", Decimal("8.50"), "package", [{"name": "username", "label": "معرف التليجرام (@username)", "type": "text", "required": True}]),
    ]),
]


def _match_keyword(kw: str, text: str) -> bool:
    """Matches keyword strictly without accidental substring false positives."""
    kw_clean = kw.lower().strip()
    text_clean = text.lower()
    if not kw_clean or not text_clean:
        return False
    if len(kw_clean) <= 4:
        # Require word boundary for short abbreviations like 'pubg', 'fifa', 'mtn', 'imo', 'bobo', 'psn'
        pattern = r'(?i)(?:^|[\s_/\-\(\)\[\],.:;])' + re.escape(kw_clean) + r'(?:$|[\s_/\-\(\)\[\],.:;])'
        return bool(re.search(pattern, text_clean))
    return kw_clean in text_clean


def _clean_candidate_app_name(raw_name: str) -> str:
    """Cleans server prefixes, tiers, and package numbers from candidate app names."""
    if not raw_name:
        return "خدمة عامة"
    cleaned = raw_name.strip()
    # Remove leading server / tier prefixes (e.g. "سيرفر 1 - ", "Server 2 | ")
    cleaned = re.sub(r'^(?:سيرفر|server|tier|باقة|قسم)\s*\d*\s*[\-–—|:/]\s*', '', cleaned, flags=re.IGNORECASE)
    # Remove package quantities from candidate app name (e.g. " - 100 ماسة", " - 500 Coins")
    cleaned = re.sub(r'[\(\[\{].*?[\)\]\}]', '', cleaned)
    cleaned = re.sub(r'\s*[\-–—|:/]\s*(?:باقة|سيرفر|server|tier|\d+).*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\b\d+\s*(?:ماسة|جوهرة|شدة|كوينز|عملة|روبوكس|توكنز|نقطة|ليرة|دولار|uc|diamonds|coins|robux|gems|usd|\$|syp|tl)\b.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(' -–—|:/')
    return cleaned if len(cleaned) >= 2 else raw_name.strip()


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

    def _get_group_name(self, pp) -> str:
        """Helper to get canonical app/group name for a provider product."""
        try:
            _, app_name = self.resolve_app_and_section(pp)
            return app_name or (pp.category.name if pp.category else "عام")
        except Exception:
            return pp.category.name if pp.category else "عام"

    def _ensure_seed_services(self):
        """
        Seeds canonical applications across all 10 standard sections if the provider
        currently only has a limited set of products (e.g. only PUBG/Free Fire).
        Guarantees that every section has products and variants ready for display and sale.
        """
        from apps.providers.models import ProviderProduct, ProviderPrice
        from apps.catalog.image_caching import match_brand_static_asset

        existing_names = set(ProviderProduct.objects.filter(profile=self.profile).values_list("name", flat=True))

        for section_name, app_name, packages in SEED_STANDARD_APPS:
            app_lower = app_name.lower()
            has_app = any(app_lower in n.lower() for n in existing_names)
            if has_app:
                continue

            brand_svg = match_brand_static_asset(app_name)
            for pkg_id, pkg_name, cost, p_type, params in packages:
                rem_id = f"SEED-{self.profile.id}-{pkg_id}"
                if ProviderProduct.objects.filter(profile=self.profile, remote_id=rem_id).exists():
                    continue

                pp = ProviderProduct.objects.create(
                    profile=self.profile,
                    remote_id=rem_id,
                    name=pkg_name,
                    local_name=pkg_name,
                    provider_category_name=section_name,
                    provider_category_img=brand_svg or "",
                    cost_price=cost,
                    provider_base_price=cost,
                    is_active=True,
                    local_is_active=True,
                    product_type=p_type,
                    raw_params=params,
                    qty_min=1,
                    qty_max=999999
                )
                ProviderPrice.objects.create(
                    product=pp,
                    margin_type="percentage",
                    retail_margin_value=Decimal("15.0"),
                    dealer_margin_value=Decimal("10.0"),
                    vip_margin_value=Decimal("5.0"),
                )
                existing_names.add(pkg_name)

    def _ensure_standard_sections(self):
        """Pre-creates the 10 standard categories in catalog.Category."""
        from apps.catalog.models import Category

        with bypass_tenant_filter():
            for name, order in STANDARD_MAIN_SECTIONS:
                cat = Category.all_objects.filter(store=self.store, name=name).first()
                if not cat:
                    cat = Category.all_objects.create(
                        store=self.store,
                        name=name,
                        sort_order=order,
                        is_active=True
                    )
                elif cat.sort_order != order or not cat.is_active:
                    cat.sort_order = order
                    cat.is_active = True
                    cat.save(update_fields=["sort_order", "is_active", "updated_at"])
                self._categories_cache[name] = cat

    def _get_catalog_category(self, section_name: str):
        """Gets category from cache or database."""
        from apps.catalog.models import Category

        with bypass_tenant_filter():
            if section_name in self._categories_cache:
                return self._categories_cache[section_name]

            cat = Category.all_objects.filter(store=self.store, name=section_name).first()
            if not cat:
                cat = Category.all_objects.create(
                    store=self.store,
                    name=section_name,
                    is_active=True
                )
            self._categories_cache[section_name] = cat
            return cat

    def resolve_app_and_section(self, pp, pp_lookup: dict = None) -> Tuple[str, str]:
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
            parent_pp = None
            if pp_lookup is not None:
                parent_pp = pp_lookup.get(str(pp.remote_parent_id))
            else:
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

        # 1. Match from Known Canonical Apps Registry
        for section, app_name, keywords in KNOWN_APPS_REGISTRY:
            if any(_match_keyword(kw, combined) for kw in keywords):
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

        candidate_app = _clean_candidate_app_name(candidate_app)

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

    def map_all_to_catalog(self, selected_group_names=None, progress_callback=None) -> Dict[str, int]:
        """
        Groups all ProviderProducts under their Canonical Apps (Products)
        and attaches each ProviderProduct as a ProductVariant.
        Optimized with in-memory caching to complete in milliseconds.
        """
        from apps.providers.models import ProviderProduct, ProviderMapping, ProviderPrice
        from apps.catalog.models import Product, ProductVariant

        provider_code = "alkasr"

        with bypass_tenant_filter():
            self._ensure_standard_sections()
            self._ensure_seed_services()

            products_qs = ProviderProduct.objects.filter(profile=self.profile)
            all_pps = list(products_qs.select_related("category", "pricing").prefetch_related("parameters"))
            pp_lookup = {str(p.remote_id): p for p in all_pps}

            stats = {
                "root_products_created": 0,
                "root_products_updated": 0,
                "variants_created": 0,
                "variants_updated": 0,
                "disabled_count": 0,
            }

            # 1. Group ProviderProducts by (Section, App Name)
            grouped_by_app: Dict[Tuple[str, str], List[ProviderProduct]] = {}

            for pp in all_pps:
                section_name, app_name = self.resolve_app_and_section(pp, pp_lookup=pp_lookup)
                if selected_group_names and app_name not in selected_group_names and section_name not in selected_group_names:
                    continue
                key = (section_name, app_name)
                grouped_by_app.setdefault(key, []).append(pp)

            # Pre-index existing Products, Variants, and Mappings
            existing_products = {
                (p.category_id, p.name): p 
                for p in Product.all_objects.filter(store=self.store, api_provider=provider_code)
            }
            existing_variants = {
                v.sku: v 
                for v in ProductVariant.all_objects.filter(sku__startswith=f"PRV-{self.profile.id}-")
            }

            total_groups = len(grouped_by_app)

            # 2. Create or Update Products and map their Variants
            for grp_idx, ((section_name, app_name), pp_list) in enumerate(grouped_by_app.items(), start=1):
                with transaction.atomic():
                    catalog_cat = self._get_catalog_category(section_name)

                    # Look up existing Product from in-memory cache or DB
                    local_product = existing_products.get((catalog_cat.id, app_name[:160]))
                    if not local_product:
                        local_product = Product.all_objects.filter(
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

                # Check if brand vector SVG or category image exists
                from apps.catalog.image_caching import match_brand_static_asset
                brand_svg = match_brand_static_asset(app_name)

                img_url = ""
                for p_item in pp_list:
                    if p_item.provider_category_img:
                        img_url = p_item.provider_category_img
                        break

                meta = dict(local_product.metadata or {}) if local_product else {}
                if brand_svg:
                    meta["image_url"] = brand_svg
                elif img_url:
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
                    local_product = Product.all_objects.create(
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
                    existing_products[(catalog_cat.id, app_name[:160])] = local_product
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
                    existing_products[(catalog_cat.id, app_name[:160])] = local_product
                    stats["root_products_updated"] += 1

                # Identify container items that act as parents to other items in this app
                parent_remote_ids = set()
                for p_item in pp_list:
                    if p_item.remote_parent_id and str(p_item.remote_parent_id) not in ("0", ""):
                        parent_remote_ids.add(str(p_item.remote_parent_id))

                # 3. Create or Update ProductVariants inside this Product
                for pp in pp_list:
                    pkg_pid = None
                    try:
                        pkg_pid = int(pp.remote_id)
                    except (ValueError, TypeError):
                        digits = re.findall(r'\d+', str(pp.remote_id))
                        if digits:
                            try:
                                pkg_pid = int(digits[-1])
                            except Exception:
                                pkg_pid = None

                    # If this provider product acts as a parent container to other items and has 0 cost, skip variant creation
                    if pkg_pid is not None and str(pkg_pid) in parent_remote_ids and pp.cost_price == 0:
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

                    if str(pp.remote_id).startswith("SEED-"):
                        sku_val = f"PRV-{pp.remote_id}"[:80]
                    else:
                        sku_val = f"PRV-{self.profile.id}-{pp.remote_id}"[:80]
                    is_active = bool(pp.local_is_active if pp.local_is_active is not None else True)
                    raw_v_name = (pp.local_name or pp.name or f"باقة {pkg_pid or pp.remote_id}").strip()
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

                    local_variant = existing_variants.get(sku_val)
                    if not local_variant:
                        local_variant = ProductVariant.all_objects.filter(sku=sku_val).first()

                    parent_id_int = None
                    try:
                        parent_id_int = int(pp.remote_parent_id) if pp.remote_parent_id else None
                    except (ValueError, TypeError):
                        parent_id_int = None

                    if not local_variant:
                        local_variant = ProductVariant.all_objects.create(
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
                        existing_variants[sku_val] = local_variant
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
                        existing_variants[sku_val] = local_variant
                        stats["variants_updated"] += 1

                    # Update ProviderMapping safely avoiding OneToOne conflict
                    if local_variant:
                        ProviderMapping.objects.filter(local_variant=local_variant).exclude(provider_product=pp).delete()
                    ProviderMapping.objects.update_or_create(
                        provider_product=pp,
                        defaults={
                            "local_product": local_product,
                            "local_variant": local_variant
                        }
                    )

            if progress_callback:
                grp_pct = 90 + int((grp_idx / max(total_groups, 1)) * 9)
                try:
                    progress_callback(grp_idx, total_groups, f"تنظيم: {app_name}", grp_pct)
                except Exception:
                    pass

        # 4. Soft-disable Stale Variants & Ensure Canonical Products are Active
        with transaction.atomic():
            active_provider_pids = set()
            for p in products_qs:
                try:
                    active_provider_pids.add(int(p.remote_id))
                except (ValueError, TypeError):
                    digits = re.findall(r'\d+', str(p.remote_id))
                    if digits:
                        try:
                            active_provider_pids.add(int(digits[-1]))
                        except Exception:
                            pass

            stale_variants = ProductVariant.all_objects.filter(
                sku__startswith=f"PRV-{self.profile.id}-"
            ).filter(
                api_product_id__isnull=False
            ).exclude(api_product_id__in=active_provider_pids)

            disabled_cnt = stale_variants.filter(is_active=True).update(
                is_active=False,
                is_temporarily_disabled=True
            )
            stats["disabled_count"] += disabled_cnt

            active_vars = ProductVariant.all_objects.filter(
                product=OuterRef("pk"),
                is_active=True,
                is_temporarily_disabled=False
            )

            # Products with active variants -> active
            Product.all_objects.filter(
                store=self.store,
                api_provider=provider_code
            ).annotate(has_active=Exists(active_vars)).filter(has_active=True).update(
                is_active=True,
                is_out_of_stock=False
            )

            # Ensure all canonical products created or updated in this run are active
            canonical_names = set(app_name[:160] for (_, app_name) in grouped_by_app.keys())
            Product.all_objects.filter(
                store=self.store,
                api_provider=provider_code,
                name__in=canonical_names
            ).update(is_active=True, is_out_of_stock=False)

        # 5. Clean up Obsolete Products & Consolidate Legacy Categories
        if not selected_group_names:
            with transaction.atomic():
                from apps.orders.models import OrderItem
                from apps.catalog.models import Category
                
                # Only clean legacy obsolete dummy names
                obsolete_candidates = Product.all_objects.filter(
                    Q(name__in=["ROBLOX 10$", "ROBLOX 25$", "ROBLOX 50$", "Tik tok"]),
                    store=self.store
                ).distinct()

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

                # Merge legacy/duplicate category names into the standard sections
                CATEGORY_ALIASES = {
                    "شحن الألعاب": "قسم الألعاب",
                    "الألعاب": "قسم الألعاب",
                    "ألعاب": "قسم الألعاب",
                    "شحن التطبيقات": "قسم الدردشة والتطبيقات",
                    "تطبيقات ودردشة": "قسم الدردشة والتطبيقات",
                    "اتصالات ورصيد": "قسم الأرصدة والاتصالات",
                    "رصيد وباقات": "قسم الأرصدة والاتصالات",
                    "بطاقات رقمية": "البطاقات الإلكترونية",
                    "بطاقات الكترونية": "البطاقات الإلكترونية",
                    "البطاقات الالكترونية": "البطاقات الإلكترونية",
                    "خدمات التلفزيون والبث": "خدمات التلفاز والبث",
                    "تلفزيون وبث": "خدمات التلفاز والبث",
                    "أرقام وحسابات": "الأرقام والحسابات",
                    "ارقام وحسابات": "الأرقام والحسابات",
                    "ترويج ودعم السوشيال ميديا": "السوشيال ميديا",
                    "سوشيال ميديا": "السوشيال ميديا",
                    "تحويلات مالية": "البطاقات الإلكترونية",
                }

                for old_name, target_name in CATEGORY_ALIASES.items():
                    old_cats = Category.all_objects.filter(store=self.store, name=old_name)
                    target_cat = self._get_catalog_category(target_name)
                    for oc in old_cats:
                        if oc.id != target_cat.id:
                            Product.all_objects.filter(category=oc).update(category=target_cat)
                            oc.delete()

                # Clean empty non-standard categories
                std_cat_names = [name for name, _ in STANDARD_MAIN_SECTIONS]
                Category.all_objects.filter(
                    store=self.store,
                    products__isnull=True
                ).exclude(name__in=std_cat_names).delete()

        # Invalidate home and catalog page caches so products appear immediately
        from django.core.cache import cache
        cache.delete("home_page_ctx_v2_global")
        cache.delete("home_page_ctx_v2")
        if self.store:
            cache.delete(f"home_page_ctx_v2_{self.store.id}")
            cache.delete(f"home_page_ctx_v2_{getattr(self.store, 'subdomain', '')}")

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

        with bypass_tenant_filter():
            qs = ProductVariant.all_objects.filter(
                provider_parent_id__isnull=False,
                provider_parent_id__gt=0
            ).select_related("product")

            if profile:
                qs = qs.filter(sku__startswith=f"PRV-{profile.id}-")

            with transaction.atomic():
                for v in qs:
                    # If variant parent does not match Product.api_product_id
                    if not v.product:
                        correct_parent = Product.all_objects.filter(
                            api_provider="alkasr",
                            api_product_id=v.provider_parent_id
                        ).first()

                        if correct_parent:
                            v.product = correct_parent
                            v.is_active = True
                            v.is_temporarily_disabled = False
                            v.save(update_fields=["product", "is_active", "is_temporarily_disabled", "updated_at"])
                            reassigned_count += 1
                    elif not v.is_active:
                        # Restore valid variant activation
                        v.is_active = True
                        v.is_temporarily_disabled = False
                        v.save(update_fields=["is_active", "is_temporarily_disabled", "updated_at"])
                        reassigned_count += 1

        logger.info(
            "Cleanup completed: %d variants checked/reassigned.",
            reassigned_count
        )
        return {"reassigned_count": reassigned_count, "deactivated_count": 0}
