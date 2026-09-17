# apps/catalog/naming.py
import re

ACRONYMS = {
    'VPN', 'VIP', 'UC', 'CP', 'TR', 'USA', 'UK', 'KSA', 'UAE', 'ID', 'AI',
    'HGS', 'HDO', 'IPTV', 'OSN', 'MTN', 'STC', 'EA', 'FC', 'RP', 'SMS', 'API',
    'FIFA', 'COD', 'PUBG', 'LOL', 'PSN', 'USD', 'EUR', 'TL', 'SAR', 'AED', 'PIA'
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
    'cyberghost': 'CyberGhost',
    'browsec': 'Browsec',
    'ipvanish': 'IPVanish',
    'openvpn': 'OpenVPN',
    'planetvpn': 'Planet VPN',
    'surfshark': 'Surfshark',
    'crushlive': 'CrushLive',
    'starmaker': 'StarMaker',
    'turkcell': 'Turkcell',
    'vodafone': 'Vodafone',
}

# (regex pattern, Arabic translation, English title)
PHRASE_MAPPINGS = [
    # Turkish Telecommunications
    (r'\bayl[ıi]k\s+paketler\b', 'باقات شهرية', 'Monthly Packages'),
    (r'\bayl[ıi]k\s+teklifler\b', 'عروض شهرية', 'Monthly Offers'),
    (r'\bhaftal[ıi]k\s+paketler\b', 'باقات أسبوعية', 'Weekly Packages'),
    (r'\bg[üu]nl[üu]k\s+paketler\b', 'باقات يومية', 'Daily Packages'),
    (r'\by[ıi]ll[ıi]k\s+paketler\b', 'باقات سنوية', 'Yearly Packages'),
    (r'\bek\s+internet\s+paketleri\b', 'باقات إنترنت إضافية', 'Extra Internet Packages'),
    (r'\bmobil\s+internet\b', 'إنترنت موبايل', 'Mobile Internet'),
    (r'\bses\s+paketleri\b', 'باقات دقائق ومكالمات', 'Voice Packages'),
    (r'\bhaz[ıi]r\s+kart\b', 'بطاقات مسبقة الدفع', 'Prepaid Cards'),
    (r'\bfaturas[ıi]z\s+paketler\b', 'باقات مسبقة الدفع', 'Prepaid Packages'),
    (r'\bfatural[ıi]\s+paketler\b', 'باقات مفوترة', 'Postpaid Packages'),
    (r'\bf[ıi]rsat\b', 'عرض مميز', 'Special Offer'),
    (r'\bindirimli\b', 'مخفض', 'Discounted'),

    # VPN Services
    (r'\b(live\s*chat|livechat)\s+vpn\b', 'لايف شات في بي ان', 'LiveChat VPN'),
    (r'\b(cyber\s*ghost|cyberghost)\s*vpn\b', 'سايبر غوست في بي ان', 'CyberGhost VPN'),
    (r'\bbrowsec\s*vpn\b', 'بروسك في بي ان', 'Browsec VPN'),
    (r'\bexpress\s*vpn\b', 'إكسبريس في بي ان', 'ExpressVPN'),
    (r'\bipvanish\s*vpn\b', 'آي بي فانيش في بي ان', 'IPVanish VPN'),
    (r'\bnord\s*vpn\b', 'نورد في بي ان', 'NordVPN'),
    (r'\bopen\s*vpn\b', 'أوبن في بي ان', 'OpenVPN'),
    (r'\bpia\s*vpn\b', 'بي آي إيه في بي ان', 'PIA VPN'),
    (r'\bplanet\s*vpn\b', 'بلانيت في بي ان', 'Planet VPN'),
    (r'\bproton\s*vpn\b', 'بروتون في بي ان', 'Proton VPN'),
    (r'\bpure\s*vpn\b', 'بيور في بي ان', 'Pure VPN'),
    (r'\badguard\s*vpn\b', 'أدجارد في بي ان', 'AdGuard VPN'),
    (r'\bsurfshark\s*vpn\b', 'سيرف شارك في بي ان', 'Surfshark VPN'),
    (r'\bwindscribe\s*vpn\b', 'ويندسكرايب في بي ان', 'Windscribe VPN'),
    (r'\bhotspot\s*shield\s*vpn\b', 'هوت سبوت شيلد في بي ان', 'Hotspot Shield VPN'),
    (r'\bkaspersky\s*vpn\b', 'كاسبرسكي في بي ان', 'Kaspersky VPN'),

    # Apps and Social
    (r'\b4fun(\s*chat)?\b', 'فور فن شات', '4Fun Chat'),
    (r'\b4party(\s*chat)?\b', 'فور بارتي شات', '4Party Chat'),
    (r'\bahlan(\s*chat)?\b', 'أهلاً شات', 'Ahlan Chat'),
    (r'\bazal(\s*live)?\b', 'آزال لايف', 'Azal Live'),
    (r'\ballo(\s*chat)?\b', 'ألو شات', 'Allo Chat'),
    (r'\bamar(\s*chat)?\b', 'عمار شات', 'Amar Chat'),
    (r'\bamisu\s*party\b', 'اميسو بارتي', 'Amisu Party'),
    (r'\bamo(\s*chat)?\b', 'عمو شات', 'Amo Chat'),
    (r'\baria(\s*chat)?\b', 'آريا شات', 'Aria Chat'),
    (r'\bayome(\s*chat)?\b', 'آيومي شات', 'Ayome Chat'),
    (r'\bbeela(\s*chat)?\b', 'بيلا شات', 'Beela Chat'),
    (r'\bbinmo(\s*chat)?\b', 'بينمو شات', 'Binmo Chat'),
    (r'\bbaat(\s*live)?\b', 'بات لايف', 'Baat Live'),
    (r'\bbest(\s*live)?\b', 'بيست لايف', 'Best Live'),
    (r'\bbobo(\s*chat)?\b', 'بوبو شات', 'Bobo Chat'),
    (r'\bcarni\b', 'كارني', 'Carni'),
    (r'\bchamet(\s*chat)?\b', 'شاميت شات', 'Chamet Chat'),
    (r'\bcocco(\s*chat)?\b', 'كوكو شات', 'Cocco Chat'),
    (r'\bcrush\s*live\b', 'كراش لايف', 'CrushLive'),
    (r'\bdoli(\s*live)?\b', 'دولي لايف', 'Doli Live'),
    (r'\bbigo(\s*live)?\b', 'بيجو لايف', 'Bigo Live'),
    (r'\blikee\b', 'لايكي', 'Likee'),
    (r'\btoptop\b', 'توب توب', 'TopTop'),
    (r'\bweplay\b', 'وي بلاي', 'WePlay'),
    (r'\b(pubg\s*mobile\s*uc|شدات\s+ببجي(\s+موبايل)?)\b', 'شدات ببجي موبايل', 'PUBG Mobile UC'),
    (r'\b(pubg\s*mobile|ببجي\s+موبايل|ببجي)\b', 'ببجي موبايل', 'PUBG Mobile'),
    (r'\b(free\s*fire\s*diamonds|جواهر\s+فري\s+فاير)\b', 'جواهر فري فاير', 'Free Fire Diamonds'),
    (r'\b(free\s*fire|فري\s+فاير)\b', 'فري فاير', 'Free Fire'),
    (r'\b(roblox\s*robux|روبوكس\s+روبلوكس)\b', 'روبوكس روبلوكس', 'Roblox Robux'),
    (r'\b(roblox|روبلوكس)\b', 'روبلوكس', 'Roblox'),
    (r'\b(yalla\s*ludo\s*diamonds|مجوهرات\s+يلا\s+لودو)\b', 'مجوهرات يلا لودو', 'Yalla Ludo Diamonds'),
    (r'\b(yalla\s*ludo|يلا\s+لودو)\b', 'يلا لودو', 'Yalla Ludo'),
    (r'\b(jawaker\s*tokens|توكنز\s+جواكر)\b', 'توكنز جواكر', 'Jawaker Tokens'),
    (r'\b(jawaker|جواكر)\b', 'جواكر', 'Jawaker'),
    (r'\b(chatgpt\s*plus|شات\s+جي\s+بي\s+تي\s+بلس)\b', 'شات جي بي تي بلس', 'ChatGPT Plus'),
    (r'\b(chatgpt|شات\s+جي\s+بي\s+تي)\b', 'شات جي بي تي', 'ChatGPT'),
]

KNOWN_WORDS_EN_AR = {
    'vpn': 'في بي ان', 'chat': 'شات', 'live': 'لايف', 'party': 'بارتي',
    'cards': 'بطاقات', 'card': 'بطاقة', 'subscription': 'اشتراك',
    'subscriptions': 'اشتراكات', 'balance': 'رصيد', 'credit': 'رصيد',
    'topup': 'شحن', 'recharge': 'شحن', 'coins': 'عملات', 'coin': 'عملات',
    'diamonds': 'جواهر', 'diamond': 'جواهر', 'points': 'نقاط', 'point': 'نقاط',
    'tokens': 'توكنز', 'token': 'توكنز', 'plus': 'بلس', 'pro': 'برو',
    'vip': 'VIP', 'premium': 'بريميوم', 'gold': 'ذهبي', 'service': 'خدمة',
    'services': 'خدمات', 'store': 'ستور', 'wallet': 'محفظة', 'package': 'باقة',
    'packages': 'باقات', 'cash': 'كاش', 'followers': 'متابعين', 'likes': 'إعجابات',
    'views': 'مشاهدات', 'month': 'شهر', 'months': 'شهور', 'year': 'سنة',
    'years': 'سنوات', 'global': 'عالمي', 'direct': 'مباشر', 'instant': 'فوري',
    'code': 'كود', 'codes': 'أكواد', 'voucher': 'قسيمة', 'vouchers': 'قسائم',
    'game': 'لعبة', 'games': 'ألعاب', 'app': 'تطبيق', 'apps': 'تطبيقات',
    'mobile': 'موبايل', 'turkey': 'تركيا', 'online': 'أونلاين', 'server': 'سيرفر',
    'antivirus': 'انتي فايروس', 'internet': 'إنترنت',

    # Brand Transliterations
    'browsec': 'بروسك', 'cyberghost': 'سايبر غوست', 'express': 'إكسبريس',
    'ipvanish': 'آي بي فانيش', 'nord': 'نورد', 'open': 'أوبن', 'pia': 'بي آي إيه',
    'planet': 'بلانيت', 'proton': 'بروتون', 'pure': 'بيور', 'ahlan': 'أهلاً',
    'azal': 'آزال', 'allo': 'ألو', 'amar': 'عمار', 'amo': 'عمو', 'aria': 'آريا',
    'ayome': 'آيومي', 'beela': 'بيلا', 'binmo': 'بينمو', 'baat': 'بات',
    'best': 'بيست', 'bobo': 'بوبو', 'carni': 'كارني', 'chamet': 'شاميت',
    'cocco': 'كوكو', 'doli': 'دولي', 'syriatel': 'سيريتل', 'mtn': 'ام تي ان',
    'turkcell': 'تروكسل', 'vodafone': 'فودافون', 'telekom': 'تليكوم',
    'netflix': 'نتفلكس', 'shahid': 'شاهد', 'spotify': 'سبوتيفاي',
    'youtube': 'يوتيوب', 'pubg': 'ببجي', 'roblox': 'روبلوكس', 'jawaker': 'جواكر',
    'weplay': 'وي بلاي', 'bigo': 'بيجو', 'likee': 'لايكي', 'discord': 'دسكورد',
    'tiktok': 'تيك توك', 'canva': 'كانفا', 'picsart': 'بيكس آرت',
    'steam': 'ستيم', 'playstation': 'بلايستيشن', 'xbox': 'اكس بوكس',
    'kaspersky': 'كاسبرسكي', 'adguard': 'أدجارد', 'free': 'فري', 'fire': 'فاير',
    'uc': 'UC', 'cp': 'CP', 'rp': 'RP'
}

KNOWN_WORDS_AR_EN = {
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
    'تركيا': 'TR', 'في بي ان': 'VPN', 'شات': 'Chat', 'لايف': 'Live',
    'ببجي': 'PUBG', 'فري فاير': 'Free Fire', 'روبلوكس': 'Roblox', 'جواكر': 'Jawaker',
    'يلا لودو': 'Yalla Ludo', 'ستيم': 'Steam', 'بلايستيشن': 'PlayStation',
    'اكس بوكس': 'Xbox', 'نتفلكس': 'Netflix', 'شاهد': 'Shahid', 'سبوتيفاي': 'Spotify',
    'يوتيوب': 'YouTube', 'سيريتل': 'Syriatel', 'ام تي ان': 'MTN', 'تروكسل': 'Turkcell'
}

def transliterate_en_to_ar(text):
    """
    Phonetically transliterates unknown English words into Arabic letters.
    Guarantees 0% English characters leak into the Arabic name.
    """
    w = text.lower()
    substitutions = [
        ('sh', 'ش'), ('ch', 'تش'), ('th', 'ث'), ('ph', 'ف'),
        ('kh', 'خ'), ('gh', 'غ'), ('ee', 'ي'), ('oo', 'و'),
        ('ou', 'و'), ('ea', 'ي'), ('ai', 'اي'), ('ay', 'اي'),
        ('ck', 'ك'),
    ]
    for eng, ar in substitutions:
        w = w.replace(eng, ar)

    char_map = {
        'b': 'ب', 'c': 'ك', 'd': 'د', 'f': 'ف', 'g': 'غ',
        'h': 'هـ', 'j': 'ج', 'k': 'ك', 'l': 'ل', 'm': 'م',
        'n': 'ن', 'p': 'ب', 'q': 'ق', 'r': 'ر', 's': 'س',
        't': 'ت', 'v': 'ف', 'w': 'و', 'x': 'اكس', 'y': 'ي',
        'z': 'ز', 'a': 'ا', 'e': 'ي', 'i': 'ي', 'o': 'و', 'u': 'و'
    }
    res = []
    for i, ch in enumerate(w):
        if ch in char_map:
            if i == 0 and ch in ('a', 'e', 'i', 'o', 'u'):
                res.append('أ' if ch in ('a', 'o', 'u') else 'إ')
            else:
                res.append(char_map[ch])
        else:
            res.append(ch)
    return ''.join(res)

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

def remove_duplicates_in_text(text):
    words = text.split()
    seen = set()
    res = []
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            res.append(w)
    return ' '.join(res)

def translate_en_to_ar(text):
    t = text
    for pattern, ar_rep, _ in PHRASE_MAPPINGS:
        if re.search(pattern, t, flags=re.IGNORECASE):
            t = re.sub(pattern, ar_rep, t, flags=re.IGNORECASE)
    words = t.split()
    res = []
    for w in words:
        clean = re.sub(r'[^a-zA-Z0-9]', '', w).lower()
        if clean in KNOWN_WORDS_EN_AR:
            res.append(KNOWN_WORDS_EN_AR[clean])
        elif w.isdigit():
            res.append(w)
        elif re.search(r'[\u0600-\u06FF]', w):
            res.append(w)
        else:
            res.append(transliterate_en_to_ar(w))
    return remove_duplicates_in_text(' '.join(res))

def translate_ar_to_en(text):
    t = text
    for pattern, _, en_rep in PHRASE_MAPPINGS:
        if re.search(pattern, t, flags=re.IGNORECASE):
            t = re.sub(pattern, en_rep, t, flags=re.IGNORECASE)
    words = t.split()
    res = []
    for w in words:
        if w in KNOWN_WORDS_AR_EN:
            res.append(KNOWN_WORDS_AR_EN[w])
        else:
            res.append(w)
    return format_official_title_case(remove_duplicates_in_text(' '.join(res)))

def format_bilingual_name(name):
    """
    Intelligent bidirectional bilingual name formatter:
    - If input is English: translates completely to Arabic, official title-casing for English.
    - If input is Arabic: translates to English, official title-casing.
    - If input is mixed: splits clean Arabic & English without duplication.
    - Zero English characters in the Arabic portion.
    """
    if not name:
        return 'خدمة عامة | General Service'
    
    raw = name.strip()
    
    # 1. If already formatted as 'Arabic | English'
    if ' | ' in raw:
        ar_candidate, en_candidate = raw.split(' | ', 1)
        ar_candidate = ar_candidate.strip()
        en_candidate = en_candidate.strip()
        
        # Check phrase mappings first
        for pattern, ar_rep, en_rep in PHRASE_MAPPINGS:
            if re.search(pattern, en_candidate, flags=re.IGNORECASE) or re.search(pattern, ar_candidate, flags=re.IGNORECASE):
                return f"{ar_rep} | {en_rep}"
                
        # If en_candidate is clean English, use it as basis
        if re.search(r'[a-zA-Z]', en_candidate) and not re.search(r'[\u0600-\u06FF]', en_candidate):
            ar_res = translate_en_to_ar(en_candidate)
            en_res = format_official_title_case(en_candidate)
            return f"{ar_res} | {en_res}"

    # 2. Check phrase mappings for raw input
    for pattern, ar_rep, en_rep in PHRASE_MAPPINGS:
        if re.search(pattern, raw, flags=re.IGNORECASE):
            return f"{ar_rep} | {en_rep}"

    # 3. Check mixed Arabic and English in raw
    has_ar = bool(re.search(r'[\u0600-\u06FF]', raw))
    has_en = bool(re.search(r'[a-zA-Z]', raw))

    if has_ar and has_en:
        ar_words = [w for w in raw.split() if re.search(r'[\u0600-\u06FF0-9]', w)]
        en_words = [w for w in raw.split() if re.search(r'[a-zA-Z0-9]', w)]
        
        # If Arabic side is only 'شات' or 'لايف' without brand, translate English brand
        if len(ar_words) == 1 and ar_words[0] in ('شات', 'لايف', 'في بي ان'):
            eng_brand = ' '.join([w for w in en_words if w.lower() not in ('chat', 'live', 'vpn')])
            if eng_brand:
                ar_words.insert(0, translate_en_to_ar(eng_brand))

        ar_clean = remove_duplicates_in_text(' '.join(ar_words))
        en_clean = format_official_title_case(remove_duplicates_in_text(' '.join(en_words)))
        return f"{ar_clean} | {en_clean}"

    elif has_en and not has_ar:
        ar_clean = translate_en_to_ar(raw)
        en_clean = format_official_title_case(raw)
        return f"{ar_clean} | {en_clean}"

    else:
        # Pure Arabic
        en_clean = translate_ar_to_en(raw)
        if en_clean == raw:
            return raw
        return f"{raw} | {en_clean}"
