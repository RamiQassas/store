# apps/catalog/naming.py
import re

ACRONYMS = {
    'VPN', 'VIP', 'UC', 'CP', 'TR', 'USA', 'UK', 'KSA', 'UAE', 'ID', 'AI',
    'HGS', 'HDO', 'IPTV', 'OSN', 'MTN', 'STC', 'EA', 'FC', 'RP', 'SMS', 'API',
    'FIFA', 'COD', 'PUBG', 'LOL', 'PSN', 'USD', 'EUR', 'TL', 'SAR', 'AED', 'PIA',
    '4K', 'GPS', 'URL', 'USDT', 'BTC', 'ETH', 'TRC20', 'ERC20'
}

SPECIAL_CASING = {
    'facebook': 'Facebook',
    'instagram': 'Instagram',
    'twitter': 'Twitter',
    'snapchat': 'Snapchat',
    'telegram': 'Telegram',
    'whatsapp': 'WhatsApp',
    'tiktok': 'TikTok',
    'youtube': 'YouTube',
    'chatgpt': 'ChatGPT',
    'openai': 'OpenAI',
    'gemini': 'Gemini',
    'discord': 'Discord',
    'spotify': 'Spotify',
    'netflix': 'Netflix',
    'shahid': 'Shahid',
    'pubg': 'PUBG',
    'freefire': 'Free Fire',
    'roblox': 'Roblox',
    'roblex': 'Roblox',
    'jawaker': 'Jawaker',
    'yallaludo': 'Yalla Ludo',
    'playstation': 'PlayStation',
    'xbox': 'Xbox',
    'steam': 'Steam',
    'itunes': 'iTunes',
    'apple': 'Apple',
    'google': 'Google',
    'canva': 'Canva',
    'picsart': 'Picsart',
    'midjourney': 'Midjourney',
    'weplay': 'WePlay',
    'toptop': 'TopTop',
    'yoyo': 'YoYo',
    'soulchill': 'SoulChill',
    'bigo': 'Bigo Live',
    'likee': 'Likee',
    'meyo': 'MeYo',
    'livu': 'LivU',
    'mixu': 'MixU',
    'tumile': 'Tumile',
    'zepeto': 'Zepeto',
    'zepito': 'Zepeto',
    'azar': 'Azar',
    'tango': 'Tango',
    'imo': 'IMO',
    'asiacell': 'Asiacell',
    'korek': 'Korek',
    'zain': 'Zain',
    'turkcell': 'Turkcell',
    'vodafone': 'Vodafone',
    'telekom': 'Telekom',
    'syriatel': 'Syriatel',
    'syriatell': 'Syriatel',
    'mtn': 'MTN',
    'stc': 'STC',
    'binance': 'Binance',
    'razer': 'Razer',
    'cyberghost': 'CyberGhost',
    'browsec': 'Browsec',
    'ipvanish': 'IPVanish',
    'openvpn': 'OpenVPN',
    'planetvpn': 'Planet VPN',
    'surfshark': 'Surfshark',
    'crushlive': 'CrushLive',
    'starmaker': 'StarMaker',
    'livechat': 'LiveChat',
    'lagofast': 'LagoFast',
}

# (regex pattern, Arabic translation, English title)
PHRASE_MAPPINGS = [
    # Social Media & Accounts
    (r'\b(auto\s*reply\s*(for\s*)?facebook|رد\s*تلقائي\s*فيس\s*بوك)\b', 'رد تلقائي فيسبوك', 'Auto Reply Facebook'),
    (r'\b(facebook\s*account|حساب\s*فيس\s*بوك)\b', 'حساب فيسبوك', 'Facebook Account'),
    (r'\b(facebook|فيس\s*بوك|فيسبوك)\b', 'فيسبوك', 'Facebook'),
    (r'\b(instagram\s*account|حساب\s*انستغرام)\b', 'حساب إنستغرام', 'Instagram Account'),
    (r'\b(instagram|انستغرام|انستقرام|إنستغرام)\b', 'إنستغرام', 'Instagram'),
    (r'\b(twitter\s*account|حساب\s*تويتر)\b', 'حساب تويتر', 'Twitter Account'),
    (r'\b(twitter|تويتر)\b', 'تويتر', 'Twitter'),
    (r'\b(snapchat|سناب\s*شات)\b', 'سناب شات', 'Snapchat'),
    (r'\b(telegram\s*account|حساب\s*تيليجرام)\b', 'حساب تيليجرام', 'Telegram Account'),
    (r'\b(telegram|تيليجرام|تليجرام|تلغرام)\b', 'تيليجرام', 'Telegram'),
    (r'\b(whatsapp\s*kazakhstan|واتساب\s*كازاخستان)\b', 'واتساب كازاخستان', 'WhatsApp Kazakhstan'),
    (r'\b(whatsapp\s*ukraine|واتساب\s*أوكرانيا)\b', 'واتساب أوكرانيا', 'WhatsApp Ukraine'),
    (r'\b(swedish\s*whatsapp|واتساب\s*سويدي)\b', 'واتساب سويدي', 'Swedish WhatsApp'),
    (r'\b(dutch\s*whatsapp|واتساب\s*هولندي)\b', 'واتساب هولندي', 'Dutch WhatsApp'),
    (r'\b(german\s*whatsapp|واتساب\s*ألماني)\b', 'واتساب ألماني', 'German WhatsApp'),
    (r'\b(british\s*whatsapp|واتساب\s*بريطاني)\b', 'واتساب بريطاني', 'British WhatsApp'),
    (r'\b(whatsapp|واتساب|واتس\s*اب)\b', 'واتساب', 'WhatsApp'),
    (r'\b(ready\s*accounts|حسابات\s*جاهزة)\b', 'حسابات جاهزة', 'Ready Accounts'),
    (r'\b(program\s*activation\s*numbers|أرقام\s*تفعيل\s*البرامج)\b', 'أرقام تفعيل البرامج', 'Program Activation Numbers'),
    (r'\b(data\s*and\s*communication|بيانات\s*واتصالات)\b', 'بيانات واتصالات', 'Data and Communication'),
    (r'\b(money\s*transfers|تحويلات\s*مالية)\b', 'تحويلات مالية', 'Money Transfers'),

    # Telecom - Iraq & Middle East
    (r'\b(asiacell\s*balance|رصيد\s*آسيا\s*سيل)\b', 'رصيد آسيا سيل', 'Asiacell Balance'),
    (r'\b(asiacell|آسيا\s*سيل|اسياسيل)\b', 'آسيا سيل', 'Asiacell'),
    (r'\b(korek\s*balance|رصيد\s*كورك)\b', 'رصيد كورك', 'Korek Balance'),
    (r'\b(korek|كورك)\b', 'كورك', 'Korek'),
    (r'\b(zain\s*iraq|زين\s*العراق)\b', 'زين العراق', 'Zain Iraq'),
    (r'\b(zain\s*tv|زين\s*تي\s*في)\b', 'زين تي في', 'Zain TV'),
    (r'\b(zain|زين)\b', 'زين', 'Zain'),
    (r'\b(syriatel|syriatell|سيريتل|سيرياتيل)\b', 'سيريتل', 'Syriatel'),
    (r'\b(mtn\s*fatura|فواتير\s*ام\s*تي\s*ان)\b', 'فواتير ام تي ان', 'MTN Fatura'),
    (r'\b(mtn|ام\s*تي\s*ان)\b', 'ام تي ان', 'MTN'),
    (r'\b(stc|اس\s*تي\s*سي|سوا)\b', 'إس تي سي', 'STC'),

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
    (r'\btl\s*turkcell\b', 'ليرات تروكسل', 'TL Turkcell'),
    (r'\btl\s*t[üu]rk\s*telekom\b', 'ليرات ترك تليكوم', 'TL Türk Telekom'),
    (r'\btl\s*vodafone\b', 'ليرات فودافون', 'TL Vodafone'),
    (r'\bturkcell\b', 'تروكسل', 'Turkcell'),
    (r'\bvodafone\b', 'فودافون', 'Vodafone'),
    (r'\bt[üu]rk\s*telekom\b', 'ترك تليكوم', 'Türk Telekom'),
    (r'\bselam\s*telekom\b', 'سلام تليكوم', 'Selam Telekom'),

    # Gaming & App Stores
    (r'\b(pubg\s*mobile\s*uc|شدات\s+ببجي(\s+موبايل)?)\b', 'شدات ببجي موبايل', 'PUBG Mobile UC'),
    (r'\b(pupg\s*turkey|ببجي\s*تركيا)\b', 'ببجي تركيا', 'PUBG Turkey'),
    (r'\b(pubg\s*mobile|ببجي\s+موبايل|ببجي)\b', 'ببجي موبايل', 'PUBG Mobile'),
    (r'\b(free\s*fire\s*diamonds|جواهر\s+فري\s+فاير)\b', 'جواهر فري فاير', 'Free Fire Diamonds'),
    (r'\b(free\s*fire\s*tr|فري\s*فاير\s*تركي)\b', 'فري فاير تركي', 'Free Fire TR'),
    (r'\b(free\s*fire|فري\s+فاير)\b', 'فري فاير', 'Free Fire'),
    (r'\b(roblox\s*robux|روبوكس\s+روبلوكس)\b', 'روبوكس روبلوكس', 'Roblox Robux'),
    (r'\b(roblex|roblox|روبلوكس)\b', 'روبلوكس', 'Roblox'),
    (r'\b(yalla\s*ludo\s*(diamonds|gold)|مجوهرات\s+يلا\s+لودو)\b', 'مجوهرات يلا لودو', 'Yalla Ludo Diamonds'),
    (r'\b(yalla\s*ludo|يلا\s+لودو)\b', 'يلا لودو', 'Yalla Ludo'),
    (r'\b(jawaker\s*tokens|توكنز\s+جواكر)\b', 'توكنز جواكر', 'Jawaker Tokens'),
    (r'\b(jawaker|جواكر)\b', 'جواكر', 'Jawaker'),
    (r'\b(clash\s*royale|كلاش\s*رويال)\b', 'كلاش رويال', 'Clash Royale'),
    (r'\b(clash\s*of\s*clans|كلاش\s*أوف\s*كلانس)\b', 'كلاش أوف كلانس', 'Clash of Clans'),
    (r'\b(mobile\s*legends|موبايل\s*ليجندز)\b', 'موبايل ليجندز', 'Mobile Legends'),
    (r'\b(razer\s*gold\s*tr|رازر\s*جولد\s*تركي)\b', 'رازر جولد تركي', 'Razer Gold TR'),
    (r'\b(razer\s*gold\s*us|razer\s*gold\s*usa|رازر\s*جولد\s*أمريكي)\b', 'رازر جولد أمريكي', 'Razer Gold US'),
    (r'\b(razer\s*gold|رازر\s*جولد)\b', 'رازر جولد', 'Razer Gold'),
    (r'\b(google\s*play\s*tr|جوجل\s*بلاي\s*تركي)\b', 'جوجل بلاي تركي', 'Google Play TR'),
    (r'\b(google\s*play\s*usa|google\s*play\s*asr|جوجل\s*بلاي\s*أمريكي)\b', 'جوجل بلاي أمريكي', 'Google Play USA'),
    (r'\b(google\s*play\s*uae|جوجل\s*بلاي\s*إماراتي)\b', 'جوجل بلاي إماراتي', 'Google Play UAE'),
    (r'\b(google\s*play|جوجل\s*بلاي)\b', 'جوجل بلاي', 'Google Play'),
    (r'\b(itunes\s*tr|آيتونز\s*تركي)\b', 'آيتونز تركي', 'iTunes TR'),
    (r'\b(itunes\s*usd|آيتونز\s*أمريكي)\b', 'آيتونز أمريكي', 'iTunes USD'),
    (r'\b(itunes\s*ger|itunes\s*germany|آيتونز\s*ألماني)\b', 'آيتونز ألماني', 'iTunes Germany'),
    (r'\b(itunes\s*neth|itunes\s*netherlands|آيتونز\s*هولندي)\b', 'آيتونز هولندي', 'iTunes Netherlands'),
    (r'\b(itunes\s*uk|آيتونز\s*بريطاني)\b', 'آيتونز بريطاني', 'iTunes UK'),
    (r'\b(itunes\s*canada|آيتونز\s*كندي)\b', 'آيتونز كندي', 'iTunes Canada'),
    (r'\b(itunes\s*spain|آيتونز\s*إسباني)\b', 'آيتونز إسباني', 'iTunes Spain'),
    (r'\b(itunes\s*belgium|آيتونز\s*بلجيكي)\b', 'آيتونز بلجيكي', 'iTunes Belgium'),
    (r'\b(itunes|آيتونز)\b', 'آيتونز', 'iTunes'),
    (r'\b(playstation|بلايستيشن)\b', 'بلايستيشن', 'PlayStation'),
    (r'\b(xbox|إكس\s*بوكس|اكس\s*بوكس)\b', 'إكس بوكس', 'Xbox'),
    (r'\b(steam|ستيم)\b', 'ستيم', 'Steam'),

    # Live & Voice Apps
    (r'\b(meyo\s*live|ميو\s*لايف)\b', 'ميو لايف', 'MeYo Live'),
    (r'\b(meyo|ميو)\b', 'ميو', 'MeYo'),
    (r'\b(livu\s*live|livu|لايف\s*يو)\b', 'لايف يو', 'LivU'),
    (r'\b(mixu|ميكس\s*يو)\b', 'ميكس يو', 'MixU'),
    (r'\b(tumile|توميل)\b', 'توميل', 'Tumile'),
    (r'\b(party\s*star|بارتي\s*ستار)\b', 'بارتي ستار', 'Party Star'),
    (r'\b(zepeto\s*zems|زيمز\s*زيبيتو)\b', 'زيمز زيبيتو', 'Zepeto Zems'),
    (r'\b(zepeto\s*coins|zepito\s*coins|عملات\s*زيبيتو)\b', 'عملات زيبيتو', 'Zepeto Coins'),
    (r'\b(zepeto|zepito|زيبيتو)\b', 'زيبيتو', 'Zepeto'),
    (r'\b(bigo\s*live|بيجو\s*لايف)\b', 'بيجو لايف', 'Bigo Live'),
    (r'\b(likee|لايكي)\b', 'لايكي', 'Likee'),
    (r'\b(toptop|توب\s*توب)\b', 'توب توب', 'TopTop'),
    (r'\b(weplay\s*gold|وي\s*بلاي\s*ذهبي)\b', 'وي بلاي ذهبي', 'WePlay Gold'),
    (r'\b(weplay|وي\s*بلاي)\b', 'وي بلاي', 'WePlay'),
    (r'\b(azar\s*chat|أزار\s*شات)\b', 'أزار شات', 'Azar Chat'),
    (r'\b(azar|أزار)\b', 'أزار', 'Azar'),
    (r'\b(tango\s*pro|تانجو\s*برو)\b', 'تانجو برو', 'Tango Pro'),
    (r'\b(tango|تانجو)\b', 'تانجو', 'Tango'),
    (r'\b(imo\s*chat|إيمو\s*شات)\b', 'إيمو شات', 'IMO Chat'),
    (r'\b(imo|إيمو)\b', 'إيمو', 'IMO'),

    # Streaming & TV
    (r'\b(blue\s*4k|بلو\s*4k)\b', 'بلو 4K', 'BLUE 4K'),
    (r'\b(look\s*tv\s*4k|look\s*tv|لوك\s*تي\s*في)\b', 'لوك تي في', 'Look TV'),
    (r'\b(barakat\s*tv|بركات\s*تي\s*في)\b', 'بركات تي في', 'Barakat TV'),
    (r'\b(shamana\s*tv|شامنا\s*تي\s*في)\b', 'شامنا تي في', 'Shamana TV'),
    (r'\b(ip\s*tv|iptv)\b', 'آي بي تي في', 'IPTV'),
    (r'\b(netflix|نتفلكس|نتفليكس)\b', 'نتفلكس', 'Netflix'),
    (r'\b(shahid|شاهد)\b', 'شاهد', 'Shahid'),
    (r'\b(spotify|سبوتيفاي)\b', 'سبوتيفاي', 'Spotify'),
    (r'\b(osn|او\s*اس\s*ان)\b', 'أو إس إن', 'OSN'),
    (r'\b(disney\+|disney|ديزني)\b', 'ديزني بلس', 'Disney+'),

    # AI & Productivity
    (r'\b(chatgpt\s*plus|شات\s+جي\s+بي\s+تي\s+بلس)\b', 'شات جي بي تي بلس', 'ChatGPT Plus'),
    (r'\b(chatgpt|شات\s+جي\s+بي\s+تي)\b', 'شات جي بي تي', 'ChatGPT'),
    (r'\b(gemini\s*pro|جيميناي\s*برو)\b', 'جيميناي برو', 'Gemini Pro'),
    (r'\b(gemini|جيميناي)\b', 'جيميناي', 'Gemini'),
    (r'\b(canva|كانفا)\b', 'كانفا', 'Canva'),
    (r'\b(picsart|بيكس\s*آرت)\b', 'بيكس آرت', 'Picsart'),
    (r'\b(lagofast\s*booster|لاغو\s*فاست)\b', 'لاغو فاست', 'LagoFast Booster'),

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
    (r'\bwindscribe(\s*traffic)?(\s*vpn)?\b', 'ويندسكرايب في بي ان', 'Windscribe VPN'),
    (r'\b(hotspot\s*shield|هوت\s*سبوت(\s*شيلد)?)(\s*vpn)?\b', 'هوت سبوت شيلد في بي ان', 'Hotspot Shield VPN'),
    (r'\b(tunnelbear|tunnelbar)(\s*vpn)?\b', 'تونيل بير في بي ان', 'TunnelBear VPN'),
    (r'\bzoog(\s*vpn)?\b', 'زوغ في بي ان', 'Zoog VPN'),
    (r'\bkaspersky\s*vpn\b', 'كاسبرسكي في بي ان', 'Kaspersky VPN'),
]

KNOWN_WORDS_EN_AR = {
    # Actions & Terms
    'facebook': 'فيسبوك', 'instagram': 'إنستغرام', 'twitter': 'تويتر', 'snapchat': 'سناب شات',
    'telegram': 'تيليجرام', 'whatsapp': 'واتساب', 'tiktok': 'تيك توك', 'youtube': 'يوتيوب',
    'asiacell': 'آسيا سيل', 'korek': 'كورك', 'zain': 'زين', 'turkcell': 'تروكسل',
    'vodafone': 'فودافون', 'telekom': 'تليكوم', 'syriatel': 'سيريتل', 'mtn': 'ام تي ان',
    'account': 'حساب', 'accounts': 'حسابات', 'ready': 'جاهز', 'auto': 'تلقائي', 'reply': 'رد',
    'vpn': 'في بي ان', 'chat': 'شات', 'live': 'لايف', 'party': 'بارتي',
    'cards': 'بطاقات', 'card': 'بطاقة', 'subscription': 'اشتراك',
    'subscriptions': 'اشتراكات', 'balance': 'رصيد', 'credit': 'رصيد',
    'topup': 'شحن', 'recharge': 'شحن', 'coins': 'عملات', 'coin': 'عملات',
    'diamonds': 'مجوهرات', 'diamond': 'مجوهرات', 'points': 'نقاط', 'point': 'نقاط',
    'tokens': 'توكنز', 'token': 'توكنز', 'plus': 'بلس', 'pro': 'برو',
    'vip': 'VIP', 'premium': 'بريميوم', 'gold': 'ذهبي', 'service': 'خدمة',
    'services': 'خدمات', 'store': 'ستور', 'wallet': 'محفظة', 'package': 'باقة',
    'packages': 'باقات', 'cash': 'كاش', 'followers': 'متابعين', 'likes': 'إعجابات',
    'views': 'مشاهدات', 'month': 'شهر', 'months': 'شهور', 'year': 'سنة',
    'years': 'سنوات', 'global': 'عالمي', 'direct': 'مباشر', 'instant': 'فوري',
    'code': 'كود', 'codes': 'أكواد', 'voucher': 'قسيمة', 'vouchers': 'قسائم',
    'game': 'لعبة', 'games': 'ألعاب', 'app': 'تطبيق', 'apps': 'تطبيقات',
    'mobile': 'موبايل', 'online': 'أونلاين', 'server': 'سيرفر',
    'antivirus': 'انتي فايروس', 'internet': 'إنترنت', 'booster': 'مسرع',
    'guaranteed': 'مضمون', 'transfer': 'تحويل', 'transfers': 'تحويلات',

    # Countries & Regions
    'turkey': 'تركيا', 'turkish': 'تركي', 'usa': 'أمريكا', 'american': 'أمريكي',
    'uk': 'بريطانيا', 'british': 'بريطاني', 'germany': 'ألمانيا', 'german': 'ألماني',
    'canada': 'كندا', 'canadian': 'كندي', 'france': 'فرنسا', 'french': 'فرنسي',
    'spain': 'إسبانيا', 'spanish': 'إسباني', 'italy': 'إيطاليا', 'italian': 'إيطالي',
    'belgium': 'بلجيكا', 'netherlands': 'هولندا', 'dutch': 'هولندي',
    'austria': 'النمسا', 'austrian': 'نمساوي', 'sweden': 'السويد', 'swedish': 'سويدي',
    'saudi': 'سعودي', 'ksa': 'السعودية', 'uae': 'الإمارات', 'kuwait': 'الكويت',
    'qatar': 'قطر', 'bahrain': 'البحرين', 'oman': 'عمان', 'iraq': 'العراق',
    'syria': 'سوريا', 'lebanon': 'لبنان', 'jordan': 'الأردن', 'egypt': 'مصر',
    'kazakhstan': 'كازاخستان', 'ukraine': 'أوكرانيا', 'vietnam': 'فيتنام',

    # Brand Transliterations
    'browsec': 'بروسك', 'cyberghost': 'سايبر غوست', 'express': 'إكسبريس',
    'ipvanish': 'آي بي فانيش', 'nord': 'نورد', 'open': 'أوبن', 'pia': 'بي آي إيه',
    'planet': 'بلانيت', 'proton': 'بروتون', 'pure': 'بيور', 'ahlan': 'أهلاً',
    'azal': 'آزال', 'allo': 'ألو', 'amar': 'عمار', 'amo': 'عمو', 'aria': 'آريا',
    'ayome': 'آيومي', 'beela': 'بيلا', 'binmo': 'بينمو', 'baat': 'بات',
    'best': 'بيست', 'bobo': 'بوبو', 'carni': 'كارني', 'chamet': 'شاميت',
    'cocco': 'كوكو', 'doli': 'دولي', 'pubg': 'ببجي', 'roblox': 'روبلوكس',
    'roblex': 'روبلوكس', 'jawaker': 'جواكر', 'weplay': 'وي بلاي', 'bigo': 'بيجو',
    'likee': 'لايكي', 'discord': 'دسكورد', 'canva': 'كانفا', 'picsart': 'بيكس آرت',
    'steam': 'ستيم', 'playstation': 'بلايستيشن', 'xbox': 'إكس بوكس',
    'kaspersky': 'كاسبرسكي', 'adguard': 'أدجارد', 'free': 'فري', 'fire': 'فاير',
    'gemini': 'جيميناي', 'binance': 'بينانس', 'razer': 'رازر',
    'meyo': 'ميو', 'livu': 'لايف يو', 'mixu': 'ميكس يو', 'tumile': 'توميل',
    'zepeto': 'زيبيتو', 'zepito': 'زيبيتو', 'zems': 'زيمز', 'azar': 'أزار',
    'tango': 'تانجو', 'imo': 'إيمو', 'for': 'لـ'
}

KNOWN_WORDS_AR_EN = {
    'بطاقات': 'Cards', 'بطاقة': 'Card', 'شحن': 'Top-Up', 'رصيد': 'Balance',
    'جواهر': 'Diamonds', 'ماسات': 'Diamonds', 'مجوهرات': 'Diamonds', 'شدات': 'UC',
    'عملات': 'Coins', 'ذهب': 'Gold', 'نقاط': 'Points', 'توكنز': 'Tokens',
    'اشتراك': 'Subscription', 'اشتراكات': 'Subscriptions', 'خدمات': 'Services',
    'خدمة': 'Service', 'كاش': 'Cash', 'متابعين': 'Followers', 'لايكات': 'Likes',
    'إعجابات': 'Likes', 'مشاهدات': 'Views', 'شهري': 'Monthly', 'سنوي': 'Yearly',
    'عالمي': 'Global', 'مباشر': 'Direct', 'فوري': 'Instant', 'أكواد': 'Codes',
    'كود': 'Code', 'قسائم': 'Vouchers', 'قسيمة': 'Voucher', 'باقات': 'Packages',
    'باقة': 'Package', 'فواتير': 'Bills', 'فاتورة': 'Bill', 'محفظة': 'Wallet',
    'ألعاب': 'Games', 'تطبيقات': 'Apps', 'حساب': 'Account', 'حسابات': 'Accounts',
    'موبايل': 'Mobile', 'تركيا': 'TR', 'في بي ان': 'VPN', 'شات': 'Chat',
    'لايف': 'Live', 'ببجي': 'PUBG', 'فري فاير': 'Free Fire', 'روبلوكس': 'Roblox',
    'جواكر': 'Jawaker', 'يلا لودو': 'Yalla Ludo', 'ستيم': 'Steam',
    'بلايستيشن': 'PlayStation', 'اكس بوكس': 'Xbox', 'إكس بوكس': 'Xbox',
    'نتفلكس': 'Netflix', 'شاهد': 'Shahid', 'سبوتيفاي': 'Spotify',
    'يوتيوب': 'YouTube', 'سيريتل': 'Syriatel', 'ام تي ان': 'MTN',
    'تروكسل': 'Turkcell', 'فودافون': 'Vodafone', 'فيسبوك': 'Facebook',
    'فيس بوك': 'Facebook', 'إنستغرام': 'Instagram', 'انستغرام': 'Instagram',
    'تويتر': 'Twitter', 'سناب شات': 'Snapchat', 'تيليجرام': 'Telegram',
    'واتساب': 'WhatsApp', 'آسيا سيل': 'Asiacell', 'كورك': 'Korek', 'زين': 'Zain'
}

def transliterate_en_to_ar(text):
    """
    Phonetically transliterates unknown English words into Arabic letters.
    Includes smart soft-c rules (c+e, c+i, c+y -> s), collapses double consonants,
    and handles silent ending e to prevent embarrassing transliterations.
    """
    if not text:
        return ''
    w = text.lower().strip()
    
    # Strip any brackets or punctuation
    w = re.sub(r'[\(\)\[\]\{\}\"\']', '', w)

    # 1. Collapse double consonants
    for double_c in ['bb', 'cc', 'dd', 'ff', 'gg', 'll', 'mm', 'nn', 'pp', 'rr', 'ss', 'tt']:
        w = w.replace(double_c, double_c[0])

    # 2. Phonetic sound clusters
    substitutions = [
        ('sh', 'ش'), ('ch', 'تش'), ('th', 'ث'), ('ph', 'ف'),
        ('kh', 'خ'), ('gh', 'غ'), ('ee', 'ي'), ('oo', 'و'),
        ('ou', 'و'), ('ea', 'ي'), ('ai', 'اي'), ('ay', 'اي'),
        ('ck', 'ك'), ('tion', 'شن'), ('sion', 'شن'),
        ('ce', 'س'), ('ci', 'سي'), ('cy', 'سي')
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
            elif i == len(w) - 1 and ch == 'e':
                # silent final e
                continue
            else:
                res.append(char_map[ch])
        else:
            res.append(ch)
    return ''.join(res)

def format_official_title_case(text):
    if not text:
        return ''
    clean_text = re.sub(r'[\(\)\[\]\{\}]', ' ', text).strip()
    words = clean_text.split()
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
    t = re.sub(r'[\(\)\[\]\{\}]', ' ', t)
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
    t = re.sub(r'[\(\)\[\]\{\}]', ' ', t)
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
    - Strips unsightly wrapping parentheses like (facebook) -> فيسبوك | Facebook.
    - Zero English characters in the Arabic portion.
    """
    if not name:
        return 'خدمة عامة | General Service'
    
    raw = name.strip()
    # Strip wrapping parentheses or brackets if present
    if (raw.startswith('(') and raw.endswith(')')) or (raw.startswith('[') and raw.endswith(']')):
        raw = raw[1:-1].strip()
    
    # 1. If already formatted as 'Arabic | English' or contains multiple pipes
    if ' | ' in raw or '|' in raw:
        parts = [p.strip() for p in re.split(r'\s*\|\s*', raw) if p.strip()]
        unique_parts = []
        for p in parts:
            if p not in unique_parts:
                unique_parts.append(p)
        if len(unique_parts) == 1:
            raw = unique_parts[0]
        elif len(unique_parts) >= 2:
            ar_candidate = unique_parts[0]
            en_candidate = unique_parts[-1]
            # Check phrase mappings first
            for pattern, ar_rep, en_rep in PHRASE_MAPPINGS:
                if re.search(pattern, en_candidate, flags=re.IGNORECASE) or re.search(pattern, ar_candidate, flags=re.IGNORECASE):
                    return f"{ar_rep} | {en_rep}"
                    
            # If en_candidate is clean English, use it as basis
            if re.search(r'[a-zA-Z]', en_candidate) and not re.search(r'[\u0600-\u06FF]', en_candidate):
                ar_res = translate_en_to_ar(en_candidate)
                en_res = format_official_title_case(en_candidate)
                return f"{ar_res} | {en_res}"
            # If ar_candidate is clean Arabic, translate to English
            if re.search(r'[\u0600-\u06FF]', ar_candidate) and not re.search(r'[a-zA-Z]', ar_candidate):
                en_res = translate_ar_to_en(ar_candidate)
                return f"{ar_candidate} | {en_res}"
            raw = f"{ar_candidate} {en_candidate}"

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
