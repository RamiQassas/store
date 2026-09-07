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

                        # Detect if the variant name represents a fixed-denomination pack (e.g. 60 UC, 360 Coins, 50 TL, 1 Month)
                        import re
                        is_fixed_denom = bool(re.search(r'\b\d+\s*(uc|gems|diamond|diamonds|coins|gold|tl|aed|sar|eur|usd|\$|€|£|month|months|year|years|شهور|شهر|سنة|عملة|جواهر|شدات|ماسات|كود|elmas)\b', variant_name, re.IGNORECASE))

                        if is_fixed_amount_package:
                            qty_type = "fixed"
                        elif qty_list and len(qty_list) > 0:
                            qty_type = "list"
                        elif is_fixed_denom:
                            qty_type = "fixed"
                        elif any(k in variant_name.lower() for k in ("فواتير", "fatura", "كاش", "cash", "تعبئة", "متابعين", "لايكات", "مشاهدات", "تعليقات", "followers", "likes", "views")):
                            qty_type = "range"
                        elif pp.product_type == "amount" and qty_max is not None and qty_min is not None and (qty_max - qty_min) >= 100:
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
                        if not is_fixed_amount_package and not is_fixed_denom:
                            if qty_min is not None and qty_min >= 100:
                                is_per_mille = True
                            elif pp.product_type == "amount" and (qty_min is None or qty_min >= 10):
                                is_per_mille = True

                        meta = {
                            "qty_type": qty_type,
                            "qty_min": 1 if (is_fixed_amount_package or is_fixed_denom) else (qty_min or 1),
                            "qty_max": 1 if is_fixed_amount_package else (999999 if is_fixed_denom else (qty_max or 999999)),
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
