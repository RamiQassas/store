import logging
from decimal import Decimal
from django.db import transaction
from apps.providers.models import ProviderMapping, ProviderProduct
from apps.catalog.models import Product, ProductVariant, Category

logger = logging.getLogger(__name__)

class AlkasrMapperService:
    def __init__(self, profile):
        self.profile = profile

    def _get_group_name(self, pp):
        """
        Determines the parent Product name (e.g. PUBG Mobile, Free Fire, Syriatel, MTN).
        """
        generic_names = {
            "null", "none", "games", "live application", "data and communication", 
            "gift cards", "tv services", "money transfers", "social media", 
            "numbers and accounts", "program activation numbers", "ألعاب", "عام",
            "شحن الألعاب", "شحن التطبيقات", "رصيد الهاتف", "تفعيل الأرقام المؤقتة",
            "ترويج ودعم السوشيال ميديا", "بطاقات الهدايا", "العملات الرقمية", "default"
        }

        # 0. If provider product has explicit category_name in its data dict
        pp_data = getattr(pp, "data", None)
        if pp_data and isinstance(pp_data, dict) and pp_data.get("category_name"):
            c_name = str(pp_data["category_name"]).strip()
            if c_name and c_name.lower() not in generic_names:
                return c_name

        cat = pp.category
        raw_cat = (cat.name if cat else "").strip()
        
        # 1. If category itself is a specific service/game (not a top-level category)
        if raw_cat and raw_cat.lower() not in generic_names:
            return raw_cat
            
        # 2. If category has a parent that is a specific service/game
        if cat and cat.parent and cat.parent.name:
            p_name = str(cat.parent.name).strip()
            if p_name.lower() not in generic_names:
                return p_name
                
        # 3. Derive from product name prefix or keyword
        prod_name = (pp.name or "").strip()
        p_low = prod_name.lower()

        # Games
        if "pubg" in p_low or "ببجي" in prod_name:
            return "ببجي موبايل (PUBG Mobile)"
        if "free fire" in p_low or "فري فاير" in prod_name:
            return "فري فاير (Free Fire)"
        if "roblox" in p_low or "روبلوكس" in prod_name:
            return "روبلوكس (Roblox)"
        if "mobile legends" in p_low or "موبايل ليجند" in prod_name:
            return "موبايل ليجندز (Mobile Legends)"
        if "call of duty" in p_low or "كول اوف ديوتي" in prod_name or "كود موبايل" in prod_name:
            return "كول أوف ديوتي (Call of Duty)"
        if "valorant" in p_low or "فالورانت" in prod_name:
            return "فالورانت (Valorant)"
        if "fortnite" in p_low or "فورتنايت" in prod_name or "فورت نايت" in prod_name:
            return "فورت نايت (Fortnite)"
        if "genshin" in p_low or "جينشين" in prod_name:
            return "جينشين إمباكت (Genshin Impact)"
        if "clash of clans" in p_low or "كلاش اوف كلانس" in prod_name:
            return "كلاش أوف كلانس (Clash of Clans)"
        if "brawl stars" in p_low or "براول ستارز" in prod_name:
            return "براول ستارز (Brawl Stars)"
        if "hay day" in p_low or "هاي داي" in prod_name:
            return "هاي داي (Hay Day)"
        if "lord" in p_low or "لوردس" in prod_name:
            return "لوردس موبايل (Lords Mobile)"

        # Apps & Streaming
        if "tiktok" in p_low or "tik tok" in p_low or "تيك توك" in prod_name:
            return "تيك توك (TikTok)"
        if "yalla" in p_low or "يلا لودو" in prod_name:
            return "يلا لودو (Yalla Ludo)"
        if "jawaker" in p_low or "جواكر" in prod_name:
            return "جواكر (Jawaker)"
        if "bigo" in p_low or "بيجو" in prod_name:
            return "بيجو لايف (Bigo Live)"
        if "likee" in p_low or "لايكي" in prod_name:
            return "لايكي (Likee)"
        if "shahid" in p_low or "شاهد" in prod_name:
            return "شاهد VIP (Shahid VIP)"
        if "netflix" in p_low or "نتفلكس" in prod_name:
            return "نتفلكس (Netflix)"
        if "disney" in p_low or "ديزني" in prod_name:
            return "ديزني بلس (+Disney)"
        if "osn" in p_low or "او اس ان" in prod_name:
            return "شبكة OSN+"
        if "anghami" in p_low or "أنغامي" in prod_name or "انغامي" in prod_name:
            return "أنغامي بلس (Anghami Plus)"
        if "spotify" in p_low or "سبوتيفاي" in prod_name:
            return "سبوتيفاي (Spotify)"
        if "discord" in p_low or "ديسكورد" in prod_name:
            return "ديسكورد نيترو (Discord Nitro)"
        if "telegram" in p_low or "تلغرام" in prod_name or "تيليجرام" in prod_name:
            return "تفعيل وتيليجرام (Telegram)"
        if "whatsapp" in p_low or "واتساب" in prod_name:
            return "تفعيل أرقام واتساب (WhatsApp)"

        # Gift Cards & Stores
        if "google play" in p_low or "جوجل بلاي" in prod_name:
            return "بطاقات جوجل بلاي (Google Play)"
        if "itunes" in p_low or "apple" in p_low or "ايتونز" in prod_name or "ابل" in prod_name:
            return "بطاقات أبل / آيتونز (Apple / iTunes)"
        if "playstation" in p_low or "psn" in p_low or "بلايستيشن" in prod_name:
            return "بطاقات بلايستيشن (PlayStation)"
        if "xbox" in p_low or "اكس بوكس" in prod_name or "إكس بوكس" in prod_name:
            return "بطاقات إكس بوكس (Xbox)"
        if "steam" in p_low or "ستيم" in prod_name:
            return "بطاقات ستيم (Steam)"
        if "razer" in p_low or "ريزر" in prod_name:
            return "بطاقات ريزر جولد (Razer Gold)"

        # Telecom & Communication
        if "syriatel" in p_low or "سيريتل" in prod_name:
            return "سيريتل كاش ورصيد (Syriatel)"
        if "mtn" in p_low or "ام تي ان" in prod_name:
            return "ام تي ان كاش ورصيد (MTN)"

        # If none matched, strip trailing denominations/numbers to group clean packages
        import re
        clean_name = re.sub(r'[\d\+\$].*', '', prod_name).strip()
        clean_name = re.sub(r'(\s*-\s*|\s*_\s*)$', '', clean_name).strip()
        if len(clean_name) >= 3 and clean_name.lower() not in generic_names:
            return clean_name

        return prod_name or "خدمة عامة"

    def _get_store_category(self, pp, store):
        # 0. Check Tafa3ol Card explicit service name from parent or data
        pp_data = getattr(pp, "data", None)
        if pp_data and isinstance(pp_data, dict) and pp_data.get("service_name"):
            srv_name = str(pp_data["service_name"]).strip()
            if srv_name:
                cat_obj, _ = Category.objects.get_or_create(
                    store=store,
                    name=srv_name,
                    defaults={"is_active": True, "sort_order": 0}
                )
                return cat_obj

        if pp.category and pp.category.parent and pp.category.parent.name:
            p_srv = str(pp.category.parent.name).strip()
            if p_srv and p_srv.lower() not in ("null", "none", "default"):
                cat_obj, _ = Category.objects.get_or_create(
                    store=store,
                    name=p_srv,
                    defaults={"is_active": True, "sort_order": 0}
                )
                return cat_obj

        curr = pp.category
        root_name = ""
        while curr:
            if curr.name and curr.name.strip().lower() not in ("null", "none"):
                root_name = curr.name.strip()
            curr = curr.parent

        category_map = {
            "games": "ألعاب",
            "شحن الألعاب": "ألعاب",
            "ألعاب": "ألعاب",
            "live application": "تطبيقات وبرامج",
            "شحن التطبيقات": "تطبيقات وبرامج",
            "تطبيقات": "تطبيقات وبرامج",
            "data and communication": "اتصالات ورصيد",
            "رصيد الهاتف": "اتصالات ورصيد",
            "اتصالات ورصيد": "اتصالات ورصيد",
            "gift cards": "بطاقات رقمية",
            "بطاقات الهدايا": "بطاقات رقمية",
            "بطاقات": "بطاقات رقمية",
            "tv services": "خدمات التلفزيون والبث",
            "money transfers": "تحويلات مالية",
            "العملات الرقمية": "العملات الرقمية",
            "social media": "ترويج ودعم السوشيال ميديا",
            "ترويج ودعم السوشيال ميديا": "ترويج ودعم السوشيال ميديا",
            "numbers and accounts": "تفعيل الأرقام المؤقتة",
            "تفعيل الأرقام المؤقتة": "تفعيل الأرقام المؤقتة",
            "program activation numbers": "تفعيل برامج واشتراكات",
        }
        
        ar_name = category_map.get(root_name.lower(), category_map.get(root_name, ""))
        
        # If root_name was generic ("عام"), infer category from product name
        if not ar_name or ar_name == "خدمات رقمية" or root_name.lower() in ("عام", "null", "none", "default"):
            p_low = (pp.name or "").lower()
            if any(k in p_low for k in ("pubg", "ببجي", "free fire", "فري فاير", "roblox", "روبلوكس", "valorant", "fortnite", "game", "لعبة", "clash", "brawl", "legends", "cod")):
                ar_name = "شحن الألعاب"
            elif any(k in p_low for k in ("tiktok", "تيك توك", "yalla", "يلا", "jawaker", "جواكر", "bigo", "بيجو", "likee", "لايكي", "shahid", "شاهد", "netflix", "نتفلكس", "spotify", "discord")):
                ar_name = "شحن التطبيقات"
            elif any(k in p_low for k in ("google play", "جوجل", "itunes", "ايتونز", "apple", "ابل", "steam", "ستيم", "playstation", "بلايستيشن", "xbox", "اكس بوكس", "razer", "ريزر", "بطاقة", "card")):
                ar_name = "بطاقات الهدايا"
            elif any(k in p_low for k in ("syriatel", "سيريتل", "mtn", "ام تي ان", "رصيد", "fatura")):
                ar_name = "رصيد الهاتف"
            elif any(k in p_low for k in ("whatsapp", "واتساب", "telegram", "تلغرام", "رقم", "number")):
                ar_name = "تفعيل الأرقام المؤقتة"
            else:
                ar_name = "خدمات رقمية"

        cat_obj, _ = Category.objects.get_or_create(
            store=store,
            name=ar_name,
            defaults={"is_active": True, "sort_order": 0}
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

    @transaction.atomic
    def map_to_catalog(self, provider_product: ProviderProduct):
        """Creates or updates a Product/Variant in the main store catalog."""
        return self.map_all_to_catalog(ProviderProduct.objects.filter(id=provider_product.id))
