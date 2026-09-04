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

        chain = self._get_category_chain(pp)

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

        # 1. If chain has Level 2 (Application / Service)
        if len(chain) >= 2:
            raw_app = chain[1].name.strip()
            if raw_app and raw_app.lower() not in generic_names:
                return app_name_map.get(raw_app, raw_app)

        # 2. Check explicit service name or category in product data
        pp_data = getattr(pp, "data", None)
        if pp_data and isinstance(pp_data, dict):
            for k in ("service_name", "category_name", "app_name"):
                val = str(pp_data.get(k) or "").strip()
                if val and val.lower() not in generic_names:
                    return app_name_map.get(val, val)

        # 3. If chain has only 1 level, but it's specific (not a generic section)
        if len(chain) == 1:
            raw_cat = chain[0].name.strip()
            if raw_cat and raw_cat.lower() not in generic_names:
                return app_name_map.get(raw_cat, raw_cat)

        # 4. Keyword matching from product name
        prod_name = (pp.name or "").strip()
        p_low = prod_name.lower()

        # Games
        if "pubg" in p_low or "ببجي" in prod_name:
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
        if "playstation" in p_low or "psn" in p_low or "بلايستيشن" in prod_name:
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
        if "turkcell" in p_low or "تروكسل" in prod_name:
            return "تروكسل تركيا (Turkcell)"

        import re
        clean_name = re.sub(r'[\d\+\$].*', '', prod_name).strip()
        clean_name = re.sub(r'(\s*-\s*|\s*_\s*)$', '', clean_name).strip()
        if len(clean_name) >= 3 and clean_name.lower() not in generic_names:
            return clean_name

        return prod_name or "خدمة عامة"

    def _get_store_category(self, pp, store):
        """
        Determines the main Store Section (Category) such as:
        - شحن الألعاب
        - شحن التطبيقات
        - اتصالات ورصيد
        - بطاقات رقمية
        - خدمات التلفزيون والبث
        - أرقام وحسابات
        - اشتراكات VPN
        - الذكاء الاصطناعي
        - برامج وتصميم
        """
        # Explicit service_name from Tafa3olcard
        pp_data = getattr(pp, "data", None)
        if pp_data and isinstance(pp_data, dict) and pp_data.get("service_name") and "tafa3ol" in (self.profile.base_url or "").lower():
            srv_name = str(pp_data["service_name"]).strip()
            if srv_name:
                cat_obj, _ = Category.objects.get_or_create(
                    store=store,
                    name=srv_name,
                    defaults={"is_active": True, "sort_order": 0}
                )
                return cat_obj

        chain = self._get_category_chain(pp)

        section_map = {
            # Alkasr exact category names
            "قسم الألعاب": "شحن الألعاب",
            "قسم الدردشة": "شحن التطبيقات",
            "قسم الأرصدة": "اتصالات ورصيد",
            "قسم الأرصدة والاتصالات": "اتصالات ورصيد",
            "البطاقات الالكترونية": "بطاقات رقمية",
            "البطاقات الإلكترونية": "بطاقات رقمية",
            "خدمات التلفاز": "خدمات التلفزيون والبث",
            "خدمات التلفاز والـ iptv": "خدمات التلفزيون والبث",
            "الأرقام والحسابات": "أرقام وحسابات",
            "الذكاء الاصطناعي": "الذكاء الاصطناعي",
            "قسم التصميم": "برامج وتصميم",
            "اشتراكات vpn": "اشتراكات VPN",
            "vpn": "اشتراكات VPN",
            
            # Common aliases and generic names
            "games": "شحن الألعاب",
            "ألعاب": "شحن الألعاب",
            "live application": "شحن التطبيقات",
            "تطبيقات": "شحن التطبيقات",
            "تطبيقات وبرامج": "شحن التطبيقات",
            "شحن التطبيقات": "شحن التطبيقات",
            "data and communication": "اتصالات ورصيد",
            "رصيد الهاتف": "اتصالات ورصيد",
            "اتصالات ورصيد": "اتصالات ورصيد",
            "gift cards": "بطاقات رقمية",
            "بطاقات الهدايا": "بطاقات رقمية",
            "بطاقات": "بطاقات رقمية",
            "tv services": "خدمات التلفزيون والبث",
            "money transfers": "تحويلات مالية",
            "social media": "ترويج ودعم السوشيال ميديا",
            "ترويج ودعم السوشيال ميديا": "ترويج ودعم السوشيال ميديا",
            "numbers and accounts": "أرقام وحسابات",
            "تفعيل الأرقام المؤقتة": "أرقام وحسابات",
            "program activation numbers": "برامج وتصميم",
        }

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
        }

        root_name = ""
        if chain:
            root_name = (chain[0].name or "").strip()

        target_name = section_map.get(root_name.lower(), section_map.get(root_name, ""))

        # If not matched by root category, infer from product name or keywords
        if not target_name or target_name == "خدمات رقمية" or root_name.lower() in ("عام", "null", "none", "default"):
            p_low = ((pp.name or "") + " " + root_name).lower()
            if any(k in p_low for k in ("pubg", "ببجي", "free fire", "فري فاير", "roblox", "روبلوكس", "valorant", "fortnite", "game", "لعبة", "clash", "brawl", "legends", "cod", "jawaker", "جواكر")):
                target_name = "شحن الألعاب"
            elif any(k in p_low for k in ("tiktok", "تيك توك", "yalla", "يلا", "bigo", "بيجو", "likee", "لايكي", "imo", "إيمو", "meyo", "azar", "livu", "chat")):
                target_name = "شحن التطبيقات"
            elif any(k in p_low for k in ("google play", "جوجل", "itunes", "ايتونز", "apple", "ابل", "steam", "ستيم", "playstation", "بلايستيشن", "xbox", "razer", "ريزر", "بطاقة", "card")):
                target_name = "بطاقات رقمية"
            elif any(k in p_low for k in ("syriatel", "سيريتل", "mtn", "ام تي ان", "turkcell", "تروكسل", "telekom", "تليكوم", "vodafone", "فودافون", "رصيد", "fatura")):
                target_name = "اتصالات ورصيد"
            elif any(k in p_low for k in ("netflix", "نتفلكس", "shahid", "شاهد", "tv", "تلفاز", "شامنا", "shamna", "iptv")):
                target_name = "خدمات التلفزيون والبث"
            elif any(k in p_low for k in ("whatsapp", "واتساب", "telegram", "تلغرام", "رقم", "number")):
                target_name = "أرقام وحسابات"
            elif any(k in p_low for k in ("vpn", "بروكسي", "nord", "express", "surfshark")):
                target_name = "اشتراكات VPN"
            elif any(k in p_low for k in ("gemini", "gpt", "chatgpt", "ذكاء", "ai")):
                target_name = "الذكاء الاصطناعي"
            elif root_name:
                target_name = root_name
            else:
                target_name = "خدمات رقمية"

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

                        if qty_list and len(qty_list) > 0:
                            qty_type = "list"
                        elif qty_max is not None and qty_min is not None and (qty_max > qty_min or (qty_min > 1 and qty_max > 1)):
                            qty_type = "range"
                        elif pp.product_type == "amount":
                            qty_type = "range"
                        elif pp.product_type in ("fixed_quantities", "specificPackage"):
                            qty_type = "list"
                        else:
                            qty_type = "fixed"

                        is_per_mille = False
                        if qty_min is not None and qty_min >= 100:
                            is_per_mille = True
                        elif pp.product_type == "amount" and (qty_min is None or qty_min >= 10):
                            is_per_mille = True

                        meta = {
                            "qty_type": qty_type,
                            "qty_min": qty_min or 1,
                            "qty_max": qty_max or 999999,
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

                        # If there is a Level 3 subcategory (e.g. اوتوماتيك 2, يدوي, أمريكي, سعودي, عضويات)
                        # and it is not already in the variant name, append it for clear identification
                        chain = self._get_category_chain(pp)
                        if len(chain) >= 3:
                            subcat_name = chain[2].name.strip()
                            if subcat_name and subcat_name.lower() not in ("null", "none", "default"):
                                if subcat_name.lower() not in variant_name.lower():
                                    variant_name = f"{variant_name} ({subcat_name})"

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
                                cost=pp.cost_price,
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
                            local_variant.cost = pp.cost_price
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
