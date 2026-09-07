from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.providers.models import ProviderProfile, ProviderProduct
from apps.providers.alkasr.mapper import AlkasrMapperService
from apps.catalog.models import Product, ProductVariant, Category

class Command(BaseCommand):
    help = 'Remaps Alkasr products into properly grouped and categorized store catalog.'

    def add_arguments(self, parser):
        parser.add_argument('--sync', action='store_true', default=False, help='Sync live catalog from provider API before remapping')

    def handle(self, *args, **options):
        do_sync = options.get('sync', False)
        CANONICAL_SECTIONS = {
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
        }

        canonical_objs = {}
        for name, order in CANONICAL_SECTIONS.items():
            cat = Category.objects.filter(name=name, store=None).first()
            if not cat:
                cat = Category.objects.filter(name=name).first()
            if not cat:
                cat = Category.objects.create(
                    name=name,
                    store=None,
                    sort_order=order,
                    is_active=True
                )
            else:
                cat.sort_order = order
                cat.is_active = True
                cat.save(update_fields=["sort_order", "is_active"])
            canonical_objs[name] = cat

        # Remap and delete only platform non-canonical categories
        non_canonical = Category.objects.filter(store=None).exclude(name__in=list(CANONICAL_SECTIONS.keys()))
        for old_cat in non_canonical:
            c_low = (old_cat.name or "").lower()
            if any(k in c_low for k in ("pubg", "ببجي", "free fire", "فري فاير", "roblox", "روبلوكس", "jawaker", "جواكر", "لعبة", "العاب", "ألعاب", "game", "سيرفر", "اوتوماتيك", "يدوي", "برايم", "نخبة", "حزم")):
                target = canonical_objs["شحن الألعاب"]
            elif any(k in c_low for k in ("tiktok", "تيك توك", "yalla", "يلا", "bigo", "بيجو", "likee", "لايكي", "imo", "ايمو", "إيمو", "azar", "أزار", "livu", "ليف", "meyo", "ميو", "party star", "soul", "star lite", "tumile", "yaahlan", "hi cat", "bermuda", "zepeto", "chat", "شات", "دردشة", "live", "لايف", "mixu")):
                target = canonical_objs["شحن التطبيقات"]
            elif any(k in c_low for k in ("turkcell", "تروكسل", "telekom", "تليكوم", "vodafone", "فودافون", "syriatel", "سيريتل", "mtn", "رصيد", "fatura", "فاتورة", "باقات", "paket", "wi-fi", "واي فاي")):
                target = canonical_objs["اتصالات ورصيد"]
            elif any(k in c_low for k in ("playstation", "بلايستيشن", "psn", "itunes", "ايتونز", "آيتونز", "apple", "ابل", "أبل", "google play", "جوجل", "steam", "ستيم", "razer", "ريزر", "بطاقات", "cards", "card", "فيزا", "visa", "voucher", "roblex")):
                target = canonical_objs["بطاقات رقمية"]
            elif any(k in c_low for k in ("netflix", "نتفلكس", "نتفليكس", "shahid", "شاهد", "shamna", "شامنا", "tv", "تلفاز", "تلفزيون", "disney", "ديزني", "osn", "او اس ان", "blue 4k", "iptv", "tango pro", "زين تي في", "بركات")):
                target = canonical_objs["خدمات التلفزيون والبث"]
            elif any(k in c_low for k in ("whatsapp", "واتساب", "telegram", "تلغرام", "تليجرام", "رقم", "أرقام", "ارقام", "number", "accounts", "حسابات جاهزة")):
                target = canonical_objs["أرقام وحسابات"]
            elif any(k in c_low for k in ("vpn", "بروكسي", "proxy", "hotspot", "lagofast", "expressvpn", "nordvpn")):
                target = canonical_objs["اشتراكات VPN"]
            elif any(k in c_low for k in ("gemini", "جيميني", "gpt", "chatgpt", "ذكاء", "ai")):
                target = canonical_objs["الذكاء الاصطناعي"]
            elif any(k in c_low for k in ("picsart", "بيكس آرت", "canva", "كانفا", "رد تلقائي", "auto reply", "تصميم", "برامج")):
                target = canonical_objs["برامج وتصميم"]
            elif any(k in c_low for k in ("حوالات", "تحويلات", "money transfer")):
                target = canonical_objs["تحويلات مالية"]
            else:
                target = canonical_objs["شحن الألعاب"]

            Product.objects.filter(category=old_cat).update(category=target)
            old_cat.delete()

        self.stdout.write(self.style.SUCCESS(f'Categories consolidated to canonical sections. Remaining: {Category.objects.count()}'))

        profiles = ProviderProfile.all_objects.filter(is_active=True)
        if not profiles.exists():
            self.stdout.write(self.style.WARNING('No active ProviderProfile found.'))
            return

        for profile in profiles:
            self.stdout.write(f'Processing profile: {profile.provider_name} (ID: {profile.id})...')
            
            # Sync from Alkasr to get latest availability and category tree only if requested
            if do_sync:
                try:
                    from services.provider.manager import ProviderManager
                    ProviderManager.sync_catalog(profile)
                    self.stdout.write(self.style.SUCCESS('Synced live availability and category tree from Alkasr.'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Sync error: {e}'))

            mapper = AlkasrMapperService(profile)
            mapper.map_all_to_catalog()
            
            # Delete auto-created dummy variants with 0 price
            ProductVariant.objects.filter(sku__startswith='AUTO-').delete()

            # Ensure all mapped variants with real prices are active
            ProductVariant.objects.filter(product__api_provider='alkasr', price__gt=0).update(is_active=True, is_temporarily_disabled=False)
            Product.objects.filter(api_provider='alkasr').update(is_active=True, is_out_of_stock=False)

            # Fix any mistakenly named products like "3 شهور"
            snap_app_cat = canonical_objs.get("شحن التطبيقات")
            duration_prods = Product.objects.filter(name__iregex=r'^\d+\s*(شهر|شهور|سنة|سنوات|أيام|يوم)')
            for dp in duration_prods:
                dp.name = "سناب شات بلس (Snapchat Plus)"
                if snap_app_cat:
                    dp.category = snap_app_cat
                dp.save(update_fields=['name', 'category'])
                for s_idx, var in enumerate(dp.variants.all(), start=1):
                    var.name = f"اشتراك 3 شهور (سيرفر {s_idx})"
                    var.save(update_fields=['name'])
                self.stdout.write(self.style.SUCCESS(f'Fixed duration product {dp.id}: renamed to سناب شات بلس (Snapchat Plus)'))

            # Clean and align TikTok packages (150 coins, 400 coins, range recharge)
            tiktok_prods = Product.objects.filter(name__icontains="تيك توك")
            for tp in tiktok_prods:
                tp.name = "تيك توك (TikTok)"
                if canonical_objs.get("شحن التطبيقات"):
                    tp.category = canonical_objs["شحن التطبيقات"]
                tp.save(update_fields=['name', 'category'])
                
                for var in tp.variants.all():
                    meta = dict(var.metadata or {})
                    rem_id = str(meta.get("remote_id") or "")
                    if rem_id == "9391" or "150" in var.name:
                        var.name = "تيك توك 150 عملة"
                        var.sort_order = 1
                        meta["qty_type"] = "fixed"
                        meta["qty_min"] = 1
                        meta["qty_max"] = 1
                        var.metadata = meta
                        if var.cost and var.cost < 1:
                            var.cost = (var.cost * 150).quantize(Decimal("0.01"))
                        if var.price and var.price < 2:
                            var.price = Decimal("2.94")
                        var.save(update_fields=['name', 'sort_order', 'metadata', 'cost', 'price'])
                    elif rem_id == "9390" or "400" in var.name:
                        var.name = "تيك توك 400 عملة"
                        var.sort_order = 2
                        meta["qty_type"] = "fixed"
                        meta["qty_min"] = 1
                        meta["qty_max"] = 1
                        var.metadata = meta
                        if var.cost and var.cost < 1:
                            var.cost = (var.cost * 400).quantize(Decimal("0.01"))
                        if var.price and var.price < 4:
                            var.price = Decimal("5.88")
                        var.save(update_fields=['name', 'sort_order', 'metadata', 'cost', 'price'])
                    elif rem_id == "9389" or "تعبئة" in var.name or "رصيد" in var.name or "tik tok" in var.name.lower():
                        var.name = "تعبئة رصيد عملات تيك توك (1,000 - 5,000,000)"
                        var.sort_order = 3
                        meta["qty_type"] = "range"
                        meta["qty_min"] = 1000
                        meta["qty_max"] = 5000000
                        var.metadata = meta
                        var.save(update_fields=['name', 'sort_order', 'metadata'])
                self.stdout.write(self.style.SUCCESS(f'Cleanly aligned TikTok (Product {tp.id}) into 3 provider options: 150 coins, 400 coins, and custom recharge.'))

            # Clean and align Syriatel packages and denominations
            syriatel_prods = Product.objects.filter(name__icontains="سيريتل") | Product.objects.filter(name__icontains="syriatel")
            for sp in syriatel_prods:
                if "تحويل" in sp.name or "transfer" in sp.name.lower():
                    continue
                sp.name = "سيريتل (Syriatel)"
                if canonical_objs.get("اتصالات ورصيد"):
                    sp.category = canonical_objs["اتصالات ورصيد"]
                sp.form_schema = {
                    "version": 1,
                    "fields": [
                        {"name": "phone", "label": "رقم الهاتف", "type": "text", "required": True, "placeholder": "مثال: 09XXXXXXXX"},
                        {"name": "service_type", "label": "نوع الخدمة", "type": "select", "options": ["رصيد تعبئة وباقات", "دفع فواتير لاحق الدفع", "سيريتل كاش"], "required": False}
                    ]
                }
                sp.save(update_fields=['name', 'category', 'form_schema'])
                for var in sp.variants.all():
                    meta = dict(var.metadata or {})
                    v_low = var.name.lower()
                    if "cash" in v_low or "كاش" in v_low:
                        var.name = "سيريتل كاش (Syriatel Cash)"
                        var.sort_order = 3
                        meta["qty_type"] = "range"
                        meta["qty_min"] = 100
                        meta["qty_max"] = 500000
                    elif "fatura" in v_low or "فاتورة" in v_low or "فواتير" in v_low:
                        var.name = "فواتير سيريتل (Syriatel Fatura)"
                        var.sort_order = 2
                        meta["qty_type"] = "range"
                        meta["qty_min"] = 100
                        meta["qty_max"] = 5000000
                    elif "credit" in v_low or "رصيد" in v_low or "باقات" in v_low:
                        var.name = "رصيد وباقات سيريتل (Syriatel Credit)"
                        var.sort_order = 1
                        meta["qty_type"] = "list"
                        meta["qty_list"] = [
                            "1000", "2000", "3000", "5000", "10000", "15000", "20000",
                            "25000", "30000", "50000", "75000", "100000", "150000",
                            "200000", "250000", "500000", "1000000"
                        ]
                    var.metadata = meta
                    var.save(update_fields=['name', 'sort_order', 'metadata'])
                self.stdout.write(self.style.SUCCESS(f'Cleanly aligned Syriatel (Product {sp.id}) with denominations and categories.'))

            # Clean and align MTN packages
            mtn_prods = Product.objects.filter(name__icontains="mtn") | Product.objects.filter(name__icontains="ام تي ان")
            for mp in mtn_prods:
                mp.name = "ام تي ان (MTN)"
                if canonical_objs.get("اتصالات ورصيد"):
                    mp.category = canonical_objs["اتصالات ورصيد"]
                mp.form_schema = {
                    "version": 1,
                    "fields": [
                        {"name": "phone", "label": "رقم الهاتف", "type": "text", "required": True, "placeholder": "مثال: 09XXXXXXXX"},
                        {"name": "service_type", "label": "نوع الخدمة", "type": "select", "options": ["رصيد تعبئة وباقات", "دفع فواتير لاحق الدفع", "ام تي ان كاش"], "required": False}
                    ]
                }
                mp.save(update_fields=['name', 'category', 'form_schema'])
                for var in mp.variants.all():
                    meta = dict(var.metadata or {})
                    v_low = var.name.lower()
                    if "fatura" in v_low or "فاتورة" in v_low or "فواتير" in v_low:
                        var.name = "فواتير ام تي ان (MTN Fatura)"
                        var.sort_order = 2
                        meta["qty_type"] = "range"
                        meta["qty_min"] = 100
                        meta["qty_max"] = 5000000
                    elif "credit" in v_low or "رصيد" in v_low or "باقات" in v_low:
                        var.name = "رصيد وباقات ام تي ان (MTN Credit)"
                        var.sort_order = 1
                        meta["qty_type"] = "list"
                        if not meta.get("qty_list"):
                            meta["qty_list"] = [
                                "1000", "2000", "3000", "5000", "10000", "15000", "20000",
                                "25000", "30000", "50000", "75000", "100000", "150000",
                                "200000", "250000", "500000", "1000000"
                            ]
                    elif "cash" in v_low or "كاش" in v_low:
                        var.name = "ام تي ان كاش (MTN Cash)"
                        var.sort_order = 3
                        meta["qty_type"] = "range"
                        meta["qty_min"] = 100
                        meta["qty_max"] = 500000
                    var.metadata = meta
                    var.save(update_fields=['name', 'sort_order', 'metadata'])
                self.stdout.write(self.style.SUCCESS(f'Cleanly aligned MTN (Product {mp.id}) with denominations and categories.'))

            # System-wide consolidation of duplicates and re-linking variants to single canonical products
            consolidation_map = [
                # Target Canonical Name, Target Category Name, list of alias regexes
                ("ببجي موبايل (PUBG Global)", "شحن الألعاب", [r"^pubg global$", r"^code$", r"^red package$"]),
                ("ببجي موبايل تركيا (PUBG TR)", "شحن الألعاب", [r"^pupg turkey$", r"^pubg tr$"]),
                ("فري فاير (Free Fire)", "شحن الألعاب", [r"^free fire$", r"^free fire tr$", r"^free fire global$"]),
                ("روبلوكس (Roblox)", "شحن الألعاب", [r"^roblex\b", r"^roblox\b", r"^بطاقات روبلوكس"]),
                ("بطاقات بلايستيشن (PlayStation)", "بطاقات رقمية", [r"^ps\s+(bahrain|kuwait|ger|usa|uk|uae|ksa|canada)", r"^playstation cards$"]),
                ("بطاقات أبل / آيتونز (iTunes)", "بطاقات رقمية", [r"^itunes\b", r"^itunes\s+"]),
                ("بطاقات جوجل بلاي (Google Play)", "بطاقات رقمية", [r"^google play\b"]),
                ("بطاقات ستيم (Steam)", "بطاقات رقمية", [r"^sudi$", r"^usa$", r"^steam global$"]),
                ("بطاقات ريزر جولد (Razer Gold)", "بطاقات رقمية", [r"^razer gold\b"]),
                ("تروكسل تركيا (Turkcell)", "اتصالات ورصيد", [r"^tl turkcell$", r"^turkcell$", r"^خدمات تروكسل$"]),
                ("ترك تليكوم تركيا (Türk Telekom)", "اتصالات ورصيد", [r"^tl türk telekom$"]),
                ("فودافون تركيا (Vodafone)", "اتصالات ورصيد", [r"^tl vodafone$", r"^vodafone$"]),
                ("تفعيل أرقام واتساب (WhatsApp)", "أرقام وحسابات", [r"^whatsapp\b", r"^واتساب يدوي"]),
                ("تليجرام بريميوم (Telegram Premium)", "أرقام وحسابات", [r"^telegram premium"]),
                ("خدمات تويتر / X (Twitter)", "ترويج ودعم السوشيال ميديا", [r"^twitter\b", r"^لايكات تويتر$", r"^متابعين تويتر$"]),
                ("خدمات إنستغرام (Instagram)", "ترويج ودعم السوشيال ميديا", [r"^خدمات الانستغرام$"]),
                ("خدمات فيسبوك (Facebook)", "ترويج ودعم السوشيال ميديا", [r"^خدمات الفيس بوك$"]),
                ("خدمات تيك توك (TikTok Services)", "ترويج ودعم السوشيال ميديا", [r"^سيرفر 1$", r"^سيرفر 2$"]),
                ("سول (Soul App)", "شحن التطبيقات", [r"^soul chat", r"^soul chill", r"^soul u", r"^soulfa"]),
                ("لايونز شات (Lions Chat)", "شحن التطبيقات", [r"^lions chat"]),
                ("ليف يو (LivU)", "شحن التطبيقات", [r"^livu\b"]),
                ("شاهد VIP (Shahid VIP)", "خدمات التلفزيون والبث", [r"^shahid\b", r"^شاهد\b"]),
                ("لايكي (Likee)", "شحن التطبيقات", [r"^likee\b"]),
                ("شحن HGS الطرق السريعة تركيا", "اتصالات ورصيد", [r"^hgs$"]),
            ]

            import re
            for target_name, cat_name, aliases in consolidation_map:
                target_cat = canonical_objs.get(cat_name)
                # Find or create primary product
                primary = Product.objects.filter(name=target_name, store=None).first()
                if not primary:
                    primary = Product.objects.create(
                        name=target_name,
                        category=target_cat,
                        store=None,
                        is_active=True,
                        api_provider='alkasr'
                    )
                else:
                    if target_cat and primary.category != target_cat:
                        primary.category = target_cat
                        primary.save(update_fields=['category'])

                for alias_pattern in aliases:
                    alias_prods = Product.objects.filter(store=None).exclude(id=primary.id).filter(name__iregex=alias_pattern)
                    for ap in alias_prods:
                        # Move all variants to primary
                        ap.variants.all().update(product=primary)
                        ap.delete()
                        self.stdout.write(self.style.SUCCESS(f"Merged duplicate product '{ap.name}' into '{target_name}'"))

            # Re-route any misfiled individual variants into their strictly correct products
            prod_ig = Product.objects.filter(name="خدمات إنستغرام (Instagram)", store=None).first()
            prod_tw = Product.objects.filter(name="خدمات تويتر / X (Twitter)", store=None).first()
            prod_fb = Product.objects.filter(name="خدمات فيسبوك (Facebook)", store=None).first()
            prod_tk_sm = Product.objects.filter(name="خدمات تيك توك (TikTok Services)", store=None).first()
            
            for var in ProductVariant.objects.filter(product__api_provider='alkasr'):
                v_low = var.name.lower()
                cur_prod_name = var.product.name if var.product else ""
                
                # Instagram variants
                if prod_ig and ("انستا" in v_low or "انستغرام" in v_low) and cur_prod_name != prod_ig.name:
                    var.product = prod_ig
                    var.save(update_fields=['product'])
                # Twitter variants
                elif prod_tw and ("تويتر" in v_low or "twitter" in v_low) and cur_prod_name != prod_tw.name:
                    var.product = prod_tw
                    var.save(update_fields=['product'])
                # Facebook variants
                elif prod_fb and ("فيسبوك" in v_low or "فيس بوك" in v_low) and cur_prod_name != prod_fb.name:
                    var.product = prod_fb
                    var.save(update_fields=['product'])
                # TikTok followers/views
                elif prod_tk_sm and any(k in v_low for k in ("متابعين تيك توك", "مشاهدات تيك توك", "لايكات تيك توك")) and cur_prod_name != prod_tk_sm.name:
                    var.product = prod_tk_sm
                    var.save(update_fields=['product'])

            # Clean any bogus products (null, placeholder, empty)
            Product.objects.filter(name__in=["null", "none", "", "."], store=None).delete()

            # Normalize and correct qty_type on all variants across catalog
            for var in ProductVariant.objects.filter(product__api_provider='alkasr'):
                meta = dict(var.metadata or {})
                v_name = var.name
                
                # Check for fixed denominations
                import re
                is_fixed = bool(re.search(r'\b\d+\s*(uc|gems|diamond|diamonds|coins|gold|tl|aed|sar|eur|usd|\$|€|£|month|months|year|years|شهور|شهر|سنة|عملة|جواهر|شدات|ماسات|كود|elmas)\b', v_name, re.IGNORECASE))
                
                if "رصيد وباقات" in v_name or "canva pro" in v_name.lower():
                    meta["qty_type"] = "list"
                elif any(k in v_name.lower() for k in ("فواتير", "كاش", "تعبئة رصيد", "متابعين", "لايكات", "مشاهدات", "تعليقات")):
                    meta["qty_type"] = "range"
                elif is_fixed:
                    meta["qty_type"] = "fixed"
                    meta["qty_min"] = 1
                    meta["qty_max"] = 999999
                
                if var.metadata != meta:
                    var.metadata = meta
                    var.save(update_fields=['metadata'])
                
                if var.metadata != meta:
                    var.metadata = meta
                    var.save(update_fields=['metadata'])

            # Clean up empty Alkasr products that have 0 variants
            empty_prods = Product.objects.filter(api_provider='alkasr', variants__isnull=True)
            empty_count = empty_prods.count()
            empty_prods.delete()
            if empty_count > 0:
                self.stdout.write(f'Cleaned up {empty_count} unused empty products.')

            # Clean and deduplicate existing order fulfillment data in the database
            from apps.orders.models import Order
            from apps.orders.provider_status import cleanup_fulfillment_data
            orders_with_fulfillment = Order.objects.exclude(fulfillment_data={}).exclude(fulfillment_data__isnull=True)
            cleaned_orders_count = 0
            for ord_obj in orders_with_fulfillment:
                old_ful = ord_obj.fulfillment_data or {}
                new_ful = cleanup_fulfillment_data(dict(old_ful))
                if old_ful != new_ful:
                    ord_obj.fulfillment_data = new_ful
                    ord_obj.save(update_fields=['fulfillment_data'])
                    cleaned_orders_count += 1
            if cleaned_orders_count > 0:
                self.stdout.write(self.style.SUCCESS(f'Cleaned up and deduplicated fulfillment data for {cleaned_orders_count} orders.'))

            from apps.stores.services import deduplicate_all_stores
            dedup_res = deduplicate_all_stores()
            self.stdout.write(self.style.SUCCESS(f'Deduplicated all stores: {dedup_res}'))

            total_cats = Category.objects.count()
            total_prods = Product.objects.filter(api_provider='alkasr').count()
            total_vars = ProductVariant.objects.filter(product__api_provider='alkasr').count()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully remapped Alkasr catalog: {total_prods} products, {total_vars} variants across {total_cats} categories.'
            ))

