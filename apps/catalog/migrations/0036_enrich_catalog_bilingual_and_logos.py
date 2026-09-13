import re
from django.db import migrations

KNOWN_NAMES = {
    # Top Games
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

    # Social & Entertainment Apps
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

    # Gift Cards
    "google play": ("بطاقات جوجل بلاي", "Google Play Cards"),
    "itunes": ("بطاقات ابل ايتونز", "Apple iTunes Cards"),
    "apple": ("بطاقات ابل ستور", "Apple Store Cards"),
    "steam": ("بطاقات ستيم", "Steam Wallet"),
    "playstation": ("بطاقات بلايستيشن", "PlayStation Store"),
    "psn": ("بطاقات بلايستيشن", "PlayStation Network"),
    "xbox": ("بطاقات اكس بوكس", "Xbox Live & Game Pass"),

    # Telecom & Balance
    "syriatel": ("سيريتل كاش", "Syriatel Cash"),
    "mtn": ("ام تي ان كاش", "MTN Cash"),
    "asiacell": ("رصيد اسياسيل", "Asiacell Balance"),
    "zain": ("رصيد زين", "Zain Balance"),
    "korek": ("رصيد كورك", "Korek Balance"),
    "turkcell": ("رصيد تركسل", "Turkcell Balance"),
    "vodafone": ("رصيد فودافون", "Vodafone Balance"),

    # Security & Tools
    "adguard": ("ادجارد في بي ان", "AdGuard VPN"),
    "nordvpn": ("نورد في بي ان", "NordVPN"),
    "expressvpn": ("اكسبريس في بي ان", "ExpressVPN"),
    "kaspersky": ("كاسبرسكي انتي فايروس", "Kaspersky Antivirus"),
}

COMMON_TRANSLATIONS = {
    "chat": "شات",
    "live": "لايف",
    "party": "بارتي",
    "voice": "صوتي",
    "room": "غرف",
    "card": "بطاقة",
    "cards": "بطاقات",
    "balance": "رصيد",
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
}


def enrich_catalog_data(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')

    for p in Product.objects.all():
        name_lower = p.name.lower().strip()

        # 1. Digital products should be available for order
        if p.is_out_of_stock:
            p.is_out_of_stock = False

        # 2. Check form_schema: provide player_id fallback if empty
        schema = p.form_schema or {}
        fields = schema.get("fields", [])
        if not fields and getattr(p, "product_type", "digital") != "physical":
            p.form_schema = {
                "version": 1,
                "fields": [
                    {
                        "label": "معرف الحساب / الايدي (Player ID)",
                        "name": "player_id",
                        "type": "text",
                        "required": True,
                        "placeholder": "أدخل معرف الحساب أو الآيدي أو رقم الهاتف..."
                    }
                ]
            }

        # 3. Bilingual naming:
        if " | " in p.name:
            parts = p.name.split(" | ", 1)
            p.name = f"{parts[0].strip()} | {parts[1].strip()}"
            p.save()
            continue

        matched = False
        for key, (ar, en) in KNOWN_NAMES.items():
            if key in name_lower:
                p.name = f"{ar} | {en}"
                matched = True
                break

        if not matched:
            if re.search(r'[a-zA-Z]', p.name) and not re.search(r'[؀-ۿ]', p.name):
                en_title = p.name.strip().title()
                words = p.name.strip().split()
                ar_words = []
                for w in words:
                    w_lower = w.lower()
                    if w_lower in COMMON_TRANSLATIONS:
                        ar_words.append(COMMON_TRANSLATIONS[w_lower])
                    else:
                        ar_words.append(w)
                ar_title = " ".join(ar_words)
                p.name = f"{ar_title} | {en_title}"
            elif re.search(r'[؀-ۿ]', p.name) and not re.search(r'[a-zA-Z]', p.name):
                p.name = f"{p.name.strip()} | {p.name.strip()}"

        p.save()


def reverse_enrich(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0035_alter_apiintegration_provider_and_more'),
    ]

    operations = [
        migrations.RunPython(enrich_catalog_data, reverse_enrich),
    ]
