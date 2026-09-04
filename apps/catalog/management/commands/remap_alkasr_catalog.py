from django.core.management.base import BaseCommand
from apps.providers.models import ProviderProfile, ProviderProduct
from apps.providers.alkasr.mapper import AlkasrMapperService
from apps.catalog.models import Product, ProductVariant, Category

class Command(BaseCommand):
    help = 'Remaps Alkasr products into properly grouped and categorized store catalog.'

    def handle(self, *args, **options):
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
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={"sort_order": order, "is_active": True}
            )
            cat.sort_order = order
            cat.is_active = True
            cat.save(update_fields=["sort_order", "is_active"])
            canonical_objs[name] = cat

        # Remap and delete all non-canonical categories
        non_canonical = Category.objects.exclude(name__in=list(CANONICAL_SECTIONS.keys()))
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
            
            # Sync from Alkasr to get latest availability and category tree
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

            # Clean up empty Alkasr products that have 0 variants
            empty_prods = Product.objects.filter(api_provider='alkasr', variants__isnull=True)
            empty_count = empty_prods.count()
            empty_prods.delete()
            if empty_count > 0:
                self.stdout.write(f'Cleaned up {empty_count} unused empty products.')

            total_cats = Category.objects.count()
            total_prods = Product.objects.filter(api_provider='alkasr').count()
            total_vars = ProductVariant.objects.filter(product__api_provider='alkasr').count()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully remapped Alkasr catalog: {total_prods} products, {total_vars} variants across {total_cats} categories.'
            ))
