# apps/catalog/naming.py
import re

ACRONYMS = {
    'VPN', 'VIP', 'UC', 'CP', 'TR', 'USA', 'UK', 'KSA', 'UAE', 'ID', 'AI',
    'HGS', 'HDO', 'IPTV', 'OSN', 'MTN', 'STC', 'EA', 'FC', 'RP', 'SMS', 'API',
    'FIFA', 'COD', 'PUBG', 'LOL', 'PSN', 'USD', 'EUR', 'TL', 'SAR', 'AED', 'HGS'
}

SPECIAL_CASING = {
    'livechat': 'LiveChat',
    'tiktok': 'TikTok',
    'playstation': 'PlayStation',
    'youtube': 'YouTube',
    'whatsapp': 'WhatsApp',
    'chatgpt': 'ChatGPT',
    'openai': 'OpenAI',
    'toptop': 'TopTop',
    'yoyo': 'YoYo',
    'soulchill': 'SoulChill',
    'freefire': 'Free Fire',
    'snapchat': 'Snapchat',
    'roblox': 'Roblox',
    'jawaker': 'Jawaker',
    'canva': 'Canva',
    'picsart': 'Picsart',
    'midjourney': 'Midjourney',
    'spotify': 'Spotify',
    'netflix': 'Netflix',
    'discord': 'Discord',
    'weplay': 'WePlay',
    'pubg': 'PUBG',
}

BIDIRECTIONAL_PHRASES = [
    ('لايف شات في بي ان', 'LiveChat VPN'),
    ('لايف شات', 'LiveChat'),
    ('في بي ان', 'VPN'),
    ('شدات ببجي موبايل', 'PUBG Mobile UC'),
    ('شدات ببجي', 'PUBG Mobile UC'),
    ('ببجي موبايل العالمية', 'PUBG Mobile Global'),
    ('ببجي موبايل تركيا', 'PUBG Mobile TR'),
    ('ببجي موبايل', 'PUBG Mobile'),
    ('ببجي', 'PUBG Mobile'),
    ('جواهر فري فاير', 'Free Fire Diamonds'),
    ('فري فاير', 'Free Fire'),
    ('روبوكس روبلوكس', 'Roblox Robux'),
    ('روبلوكس', 'Roblox'),
    ('توكنز جواكر', 'Jawaker Tokens'),
    ('جواكر', 'Jawaker'),
    ('مجوهرات يلا لودو', 'Yalla Ludo Diamonds'),
    ('يلا لودو', 'Yalla Ludo'),
    ('براول ستارز', 'Brawl Stars'),
    ('كلاش اوف كلانس', 'Clash of Clans'),
    ('كلاش رويال', 'Clash Royale'),
    ('موبايل ليجندز', 'Mobile Legends'),
    ('كول اوف ديوتي موبايل', 'Call of Duty Mobile'),
    ('كول اوف ديوتي', 'Call of Duty'),
    ('اف سي موبايل', 'EA FC Mobile'),
    ('فيفا موبايل', 'FIFA Mobile'),
    ('فالورانت', 'Valorant'),
    ('ليج اوف ليجيندز', 'League of Legends'),
    ('اونور اوف كينجز', 'Honor of Kings'),
    ('بطاقات ستيم', 'Steam Cards'),
    ('محفظة ستيم', 'Steam Wallet'),
    ('ستيم', 'Steam'),
    ('بطاقات بلايستيشن', 'PlayStation Cards'),
    ('متجر بلايستيشن', 'PlayStation Store'),
    ('بلايستيشن', 'PlayStation'),
    ('بطاقات جوجل بلاي', 'Google Play Cards'),
    ('جوجل بلاي', 'Google Play'),
    ('بطاقات ابل ايتونز', 'Apple iTunes Cards'),
    ('ابل ايتونز', 'Apple iTunes'),
    ('بطاقات ابل', 'Apple Cards'),
    ('ابل ستور', 'Apple Store'),
    ('ابل', 'Apple'),
    ('بطاقات ريزر جولد', 'Razer Gold Cards'),
    ('ريزر جولد', 'Razer Gold'),
    ('بطاقات اكس بوكس', 'Xbox Cards'),
    ('اكس بوكس', 'Xbox'),
    ('اشتراك نتفلكس بريميوم', 'Netflix Premium Subscription'),
    ('نتفلكس بريميوم', 'Netflix Premium'),
    ('اشتراك نتفلكس', 'Netflix Subscription'),
    ('نتفلكس', 'Netflix'),
    ('نتفليكس', 'Netflix'),
    ('اشتراك شاهد VIP', 'Shahid VIP Subscription'),
    ('شاهد vip', 'Shahid VIP'),
    ('شاهد', 'Shahid VIP'),
    ('اشتراك سبوتيفاي بريميوم', 'Spotify Premium Subscription'),
    ('سبوتيفاي بريميوم', 'Spotify Premium'),
    ('سبوتيفاي', 'Spotify'),
    ('يوتيوب بريميوم', 'YouTube Premium'),
    ('يوتيوب', 'YouTube'),
    ('سناب شات بلس', 'Snapchat Plus'),
    ('سناب شات', 'Snapchat'),
    ('تيك توك', 'TikTok'),
    ('تيليجرام بريميوم', 'Telegram Premium'),
    ('تيليجرام', 'Telegram'),
    ('تليجرام', 'Telegram'),
    ('دسكورد نيترو', 'Discord Nitro'),
    ('دسكورد', 'Discord'),
    ('شات جي بي تي بلس', 'ChatGPT Plus'),
    ('شات جي بي تي', 'ChatGPT'),
    ('أوبن إيه آي', 'OpenAI'),
    ('كانفا برو', 'Canva Pro'),
    ('كانفا', 'Canva'),
    ('بيكس آرت', 'Picsart'),
    ('ميدجورني', 'Midjourney'),
    ('سيريتل كاش', 'Syriatel Cash'),
    ('رصيد سيريتل', 'Syriatel Balance'),
    ('سيريتل', 'Syriatel'),
    ('ام تي ان كاش', 'MTN Cash'),
    ('رصيد ام تي ان', 'MTN Balance'),
    ('ام تي ان', 'MTN'),
    ('تركسل', 'Turkcell'),
    ('تروكسل', 'Turkcell'),
    ('فودافون', 'Vodafone'),
    ('ترك تليكوم', 'Türk Telekom'),
    ('تليكوم', 'Türk Telekom'),
    ('اسياسيل', 'Asiacell'),
    ('زين', 'Zain'),
    ('كورك', 'Korek'),
    ('بيجو لايف', 'Bigo Live'),
    ('لايكي', 'Likee'),
    ('سول تشيل', 'SoulChill'),
    ('يويو شات', 'YoYo Chat'),
    ('ليف يو', 'LivU'),
    ('تانغو لايف', 'Tango Live'),
    ('نورد في بي ان', 'NordVPN'),
    ('اكسبريس في بي ان', 'ExpressVPN'),
    ('ادجارد في بي ان', 'AdGuard VPN'),
    ('ادجارد', 'AdGuard'),
    ('سايبر جوست في بي ان', 'CyberGhost VPN'),
    ('سايبر جوست', 'CyberGhost'),
    ('كاسبرسكي انتي فايروس', 'Kaspersky Antivirus'),
    ('كاسبرسكي', 'Kaspersky'),
]

WORDS_EN_TO_AR = {
    'vpn': 'في بي ان', 'cards': 'بطاقات', 'card': 'بطاقة', 'subscription': 'اشتراك',
    'subscriptions': 'اشتراكات', 'balance': 'رصيد', 'credit': 'رصيد', 'topup': 'شحن',
    'top-up': 'شحن', 'recharge': 'شحن', 'coins': 'عملات', 'coin': 'عملات',
    'diamonds': 'جواهر', 'diamond': 'جواهر', 'points': 'نقاط', 'point': 'نقاط',
    'gems': 'جواهر', 'gem': 'جواهر', 'tokens': 'توكنز', 'token': 'توكنز',
    'plus': 'بلس', 'pro': 'برو', 'vip': 'VIP', 'premium': 'بريميوم',
    'gold': 'ذهبي', 'service': 'خدمة', 'services': 'خدمات', 'chat': 'شات',
    'live': 'لايف', 'store': 'ستور', 'wallet': 'محفظة', 'package': 'باقة',
    'packages': 'باقات', 'cash': 'كاش', 'followers': 'متابعين', 'likes': 'إعجابات',
    'views': 'مشاهدات', 'month': 'شهر', 'months': 'شهور', 'year': 'سنة',
    'years': 'سنوات', 'global': 'عالمي', 'direct': 'مباشر', 'instant': 'فوري',
    'code': 'كود', 'codes': 'أكواد', 'voucher': 'قسيمة', 'vouchers': 'قسائم',
    'game': 'لعبة', 'games': 'ألعاب', 'app': 'تطبيق', 'apps': 'تطبيقات',
    'antivirus': 'انتي فايروس', 'mobile': 'موبايل', 'turkey': 'تركيا',
}

WORDS_AR_TO_EN = {
    'بطاقات': 'Cards', 'بطاقة': 'Card', 'شحن': 'Top-Up', 'رصيد': 'Balance',
    'جواهر': 'Diamonds', 'ماسات': 'Diamonds', 'شدات': 'UC', 'عملات': 'Coins',
    'نقاط': 'Points', 'توكنز': 'Tokens', 'اشتراك': 'Subscription',
    'اشتراكات': 'Subscriptions', 'خدمات': 'Services', 'خدمة': 'Service',
    'كاش': 'Cash', 'متابعين': 'Followers', 'لايكات': 'Likes', 'إعجابات': 'Likes',
    'مشاهدات': 'Views', 'شهري': 'Monthly', 'سنوي': 'Yearly', 'عالمي': 'Global',
    'مباشر': 'Direct', 'فوري': 'Instant', 'أكواد': 'Codes', 'كود': 'Code',
    'قسائم': 'Vouchers', 'قسيمة': 'Voucher', 'باقات': 'Packages', 'باقة': 'Package',
    'فواتير': 'Bills', 'فاتورة': 'Bill', 'محفظة': 'Wallet', 'ألعاب': 'Games',
    'تطبيقات': 'Apps', 'حساب': 'Account', 'حسابات': 'Accounts', 'موبايل': 'Mobile',
    'تركيا': 'TR',
}

def format_official_title_case(text):
    if not text:
        return ''
    words = text.strip().split()
    res = []
    for w in words:
        clean_w = re.sub(r'[^a-zA-Z0-9]', '', w).lower()
        upper_w = w.upper()
        if clean_w in SPECIAL_CASING:
            res.append(SPECIAL_CASING[clean_w])
        elif upper_w in ACRONYMS:
            res.append(upper_w)
        elif w.isdigit() or re.match(r'^\d+[a-zA-Z]*$', w):
            res.append(w.upper() if any(w.upper().endswith(a) for a in ACRONYMS) else w)
        else:
            res.append(w.capitalize())
    return ' '.join(res)

def translate_en_to_ar(text):
    t = text
    for ar_p, en_p in BIDIRECTIONAL_PHRASES:
        pattern = r'\b' + re.escape(en_p.lower()) + r'\b'
        if re.search(pattern, t.lower()):
            t = re.sub(pattern, ar_p, t, flags=re.IGNORECASE)
    words = t.split()
    res = []
    for w in words:
        clean = re.sub(r'[^a-zA-Z0-9]', '', w).lower()
        if clean in WORDS_EN_TO_AR:
            res.append(WORDS_EN_TO_AR[clean])
        else:
            res.append(w)
    return ' '.join(res)

def translate_ar_to_en(text):
    t = text
    for ar_p, en_p in BIDIRECTIONAL_PHRASES:
        if ar_p in t:
            t = t.replace(ar_p, en_p)
    words = t.split()
    res = []
    for w in words:
        if w in WORDS_AR_TO_EN:
            res.append(WORDS_AR_TO_EN[w])
        else:
            res.append(w)
    return format_official_title_case(' '.join(res))

def format_bilingual_name(name):
    if not name:
        return 'خدمة عامة | General Service'
    raw = name.strip()
    
    # 1. If already formatted as 'Arabic | English'
    if ' | ' in raw:
        ar_part, en_part = raw.split(' | ', 1)
        ar_part = ar_part.strip()
        en_part = format_official_title_case(en_part.strip())
        if '\ufffd' in ar_part or not re.search(r'[\u0600-\u06FF]', ar_part):
            ar_part = translate_en_to_ar(en_part)
        else:
            ar_part = translate_en_to_ar(ar_part)
        return f'{ar_part} | {en_part}'
        
    # 2. If 'Arabic (English)'
    m = re.match(r'^(.*?)\s*\((.*?)\)$', raw)
    if m:
        ar_p = m.group(1).strip()
        en_p = m.group(2).strip()
        if re.search(r'[؀-ۿ]', ar_p) and re.search(r'[a-zA-Z]', en_p):
            return f'{ar_p} | {format_official_title_case(en_p)}'
            
    has_ar = bool(re.search(r'[؀-ۿ]', raw))
    has_en = bool(re.search(r'[a-zA-Z]', raw))
    
    if has_en and not has_ar:
        ar_side = translate_en_to_ar(raw)
        en_side = format_official_title_case(raw)
        return f'{ar_side} | {en_side}'
        
    if has_ar and not has_en:
        ar_side = raw
        en_side = translate_ar_to_en(raw)
        return f'{ar_side} | {en_side}'
        
    # Mixed
    en_side = format_official_title_case(raw)
    ar_side = translate_en_to_ar(raw)
    return f'{ar_side} | {en_side}'
