from django.db import migrations

CANONICAL_SECTIONS = {
    شحن الألعاب: 1,
    شحن التطبيقات: 2,
    اتصالات ورصيد: 3,
    بطاقات رقمية: 4,
    خدمات التلفزيون والبث: 5,
    أرقام وحسابات: 6,
    اشتراكات VPN: 7,
    الذكاء الاصطناعي: 8,
    برامج وتصميم: 9,
    تحويلات مالية: 10,
}

def consolidate_categories(apps, schema_editor):
    Category = apps.get_model('catalog', 'Category')
    Product = apps.get_model('catalog', 'Product')

    canonical_objs = {}
    for name, order in CANONICAL_SECTIONS.items():
        cat, _ = Category.objects.get_or_create(
            name=name,
            defaults={sort_order: order, is_active: True}
        )
        cat.sort_order = order
        cat.is_active = True
        cat.save(update_fields=[sort_order, is_active])
        canonical_objs[name] = cat

    non_canonical = Category.objects.exclude(name__in=list(CANONICAL_SECTIONS.keys()))
    for old_cat in non_canonical:
        c_low = (old_cat.name or ").lower()
 if any(k in c_low for k in (pubg, ببجي, free fire, فري فاير, roblox, روبلوكس, jawaker, جواكر, لعبة, العاب, ألعاب, game, سيرفر, اوتوماتيك, يدوي, برايم, نخبة, حزم)):
 target = canonical_objs[شحن الألعاب]
 elif any(k in c_low for k in (tiktok, تيك توك, yalla, يلا, bigo, بيجو, likee, لايكي, imo, ايمو, إيمو, azar, أزار, livu, ليف, meyo, ميو, party star, soul, star lite, tumile, yaahlan, hi cat, bermuda, zepeto, chat, شات, دردشة, live, لايف, mixu)):
 target = canonical_objs[شحن التطبيقات]
 elif any(k in c_low for k in (turkcell, تروكسل, telekom, تليكوم, vodafone, فودافون, syriatel, سيريتل, mtn, رصيد, fatura, فاتورة, باقات, paket, wi-fi, واي فاي)):
 target = canonical_objs[اتصالات ورصيد]
 elif any(k in c_low for k in (playstation, بلايستيشن, psn, itunes, ايتونز, آيتونز, apple, ابل, أبل, google play, جوجل, steam, ستيم, razer, ريزر, بطاقات, cards, card, فيزا, visa, voucher, roblex)):
 target = canonical_objs[بطاقات رقمية]
 elif any(k in c_low for k in (netflix, نتفلكس, نتفليكس, shahid, شاهد, shamna, شامنا, tv, تلفاز, تلفزيون, disney, ديزني, osn, او اس ان, blue 4k, iptv, tango pro, زين تي في, بركات)):
 target = canonical_objs[خدمات التلفزيون والبث]
 elif any(k in c_low for k in (whatsapp, واتساب, telegram, تلغرام, تليجرام, رقم, أرقام, ارقام, number, accounts, حسابات جاهزة)):
 target = canonical_objs[أرقام وحسابات]
 elif any(k in c_low for k in (vpn, بروكسي, proxy, hotspot, lagofast, expressvpn, nordvpn)):
 target = canonical_objs[اشتراكات VPN]
 elif any(k in c_low for k in (gemini, جيميني, gpt, chatgpt, ذكاء, ai)):
 target = canonical_objs[الذكاء الاصطناعي]
 elif any(k in c_low for k in (picsart, بيكس آرت, canva, كانفا, رد تلقائي, auto reply, تصميم, برامج)):
 target = canonical_objs[برامج وتصميم]
 elif any(k in c_low for k in (حوالات, تحويلات, money transfer)):
 target = canonical_objs[تحويلات مالية]
 else:
 target = canonical_objs[شحن الألعاب]

 Product.objects.filter(category=old_cat).update(category=target)
 old_cat.delete()

def noop(apps, schema_editor):
 pass

class Migration(migrations.Migration):

 dependencies = [
 ('catalog', '0031_alter_product_category'),
 ]

 operations = [
 migrations.RunPython(consolidate_categories, noop),
 ]
