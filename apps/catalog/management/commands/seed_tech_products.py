import os, sys, re, uuid
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from apps.catalog.models import Category, Product, ProductVariant
from apps.common.tenant_utils import bypass_tenant_filter

BRAND_ACCENTS = {
    "Apple": (245, 158, 11),
    "Samsung": (56, 189, 248),
    "Xiaomi": (249, 115, 22),
    "Poco": (250, 204, 21),
    "Infinix": (16, 185, 129),
    "Honor": (99, 102, 241),
    "Tecno": (59, 130, 246),
    "Itel": (239, 68, 68),
    "Modio": (168, 85, 247),
    "ZTE": (236, 72, 153),
    "Sumax": (244, 63, 94),
    "Reekoo": (20, 184, 166),
    "Huawei / Generic": (56, 189, 248)
}

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '_', s)
    return s[:45]

def generate_device_image(filename, brand, model_name, category_type="phone"):
    target_dir = os.path.join(settings.MEDIA_ROOT, "products", "main")
    os.makedirs(target_dir, exist_ok=True)
    out_file = os.path.join(target_dir, filename)
    if os.path.exists(out_file):
        return f"products/main/{filename}"

    W, H = 800, 800
    accent = BRAND_ACCENTS.get(brand, (56, 189, 248))
    img = Image.new('RGB', (W, H), color=(11, 15, 26))
    draw = ImageDraw.Draw(img)

    for r in range(360, 0, -12):
        factor = (1 - r / 360)
        glow_color = (
            min(255, 11 + int(accent[0] * 0.16 * factor)),
            min(255, 15 + int(accent[1] * 0.16 * factor)),
            min(255, 26 + int(accent[2] * 0.22 * factor))
        )
        draw.ellipse([W//2 - r, H//2 - r - 20, W//2 + r, H//2 + r - 20], fill=glow_color)

    try:
        font_large = ImageFont.truetype("arial.ttf", 36)
        font_medium = ImageFont.truetype("arial.ttf", 26)
        font_small = ImageFont.truetype("arial.ttf", 20)
        font_badge = ImageFont.truetype("arial.ttf", 18)
    except:
        font_large = font_medium = font_small = font_badge = ImageFont.load_default()

    if category_type == "phone":
        pw, ph = 260, 510
        px1 = (W - pw) // 2
        py1 = (H - ph) // 2 - 40
        px2 = px1 + pw
        py2 = py1 + ph
        draw.rounded_rectangle([px1 - 4, py1 - 4, px2 + 4, py2 + 4], radius=38, fill=(35, 45, 62), outline=(100, 116, 139), width=2)
        draw.rounded_rectangle([px1, py1, px2, py2], radius=34, fill=(15, 20, 32), outline=(30, 41, 59), width=2)
        draw.rounded_rectangle([px1 + 8, py1 + 8, px2 - 8, py2 - 8], radius=28, fill=(8, 11, 18))

        sx1, sy1 = px1 + 12, py1 + 12
        sx2, sy2 = px2 - 12, py2 - 12
        draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=24, fill=(13, 17, 30))
        draw.arc([sx1 - 20, sy1 + 100, sx2 + 60, sy2 - 40], start=0, end=180, fill=accent, width=5)
        draw.ellipse([W//2 - 45, H//2 - 90, W//2 + 45, H//2], fill=(accent[0]//4, accent[1]//4, accent[2]//4))
        draw.rounded_rectangle([W//2 - 24, py1 + 16, W//2 + 24, py1 + 32], radius=8, fill=(0, 0, 0))
        draw.ellipse([W//2 - 8, py1 + 20, W//2 + 8, py1 + 28], fill=(30, 30, 45))
        draw.rounded_rectangle([W//2 - 35, py2 - 22, W//2 + 35, py2 - 18], radius=2, fill=(148, 163, 184))

    elif category_type == "tablet":
        tw, th = 440, 520
        tx1 = (W - tw) // 2
        ty1 = (H - th) // 2 - 40
        tx2 = tx1 + tw
        ty2 = ty1 + th
        draw.rounded_rectangle([tx1 - 4, ty1 - 4, tx2 + 4, ty2 + 4], radius=28, fill=(45, 55, 75), outline=(110, 125, 145), width=2)
        draw.rounded_rectangle([tx1, ty1, tx2, ty2], radius=24, fill=(15, 20, 32))
        draw.rounded_rectangle([tx1 + 10, ty1 + 10, tx2 - 10, ty2 - 10], radius=18, fill=(8, 11, 20))
        draw.ellipse([W//2 - 75, H//2 - 80, W//2 + 75, H//2 + 70], fill=(accent[0]//5, accent[1]//5, accent[2]//5))
        draw.arc([tx1 + 40, ty1 + 80, tx2 - 40, ty2 - 80], start=30, end=210, fill=accent, width=5)
        draw.ellipse([W//2 - 5, ty1 + 14, W//2 + 5, ty1 + 24], fill=(0, 0, 0))

    elif category_type == "charger":
        cx1, cy1 = W//2 - 90, H//2 - 160
        cx2, cy2 = W//2 + 90, H//2 + 40
        draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=20, fill=(28, 33, 46), outline=(70, 80, 100), width=2)
        draw.rectangle([W//2 - 50, cy1 - 40, W//2 - 25, cy1], fill=(160, 175, 200))
        draw.rectangle([W//2 + 25, cy1 - 40, W//2 + 50, cy1], fill=(160, 175, 200))
        draw.text((W//2 - 35, cy2 - 65), "45W", fill=accent, font=font_large)
        draw.text((W//2 - 60, cy2 - 28), "FAST CHARGER", fill=(148, 163, 184), font=font_small)

    elif category_type == "router":
        rx1, ry1 = W//2 - 160, H//2 - 60
        rx2, ry2 = W//2 + 160, H//2 + 120
        draw.line([W//2 - 110, ry1 - 120, W//2 - 110, ry1], fill=(70, 80, 100), width=8)
        draw.line([W//2 + 110, ry1 - 120, W//2 + 110, ry1], fill=(70, 80, 100), width=8)
        draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=18, fill=(25, 30, 45), outline=(60, 75, 100), width=2)
        for i in range(5):
            draw.ellipse([W//2 - 60 + i*30, ry1 + 30, W//2 - 46 + i*30, ry1 + 44], fill=accent)
        draw.text((W//2 - 45, ry2 - 45), "4G ROUTER", fill=(255, 255, 255), font=font_medium)

    draw.rounded_rectangle([60, H - 120, W - 60, H - 35], radius=16, fill=(13, 17, 28), outline=(35, 45, 65), width=2)
    draw.rounded_rectangle([75, H - 108, 195, H - 74], radius=8, fill=(accent[0]//4, accent[1]//4, accent[2]//4), outline=accent, width=1)
    draw.text((88, H - 104), brand.upper(), fill=accent, font=font_badge)
    display_model = model_name if len(model_name) < 28 else model_name[:26] + "..."
    draw.text((210, H - 104), display_model, fill=(255, 255, 255), font=font_medium)
    draw.text((W - 250, H - 70), "ORIGINAL HARDWARE", fill=(52, 211, 153), font=font_badge)

    img.save(out_file, quality=92)
    return f"products/main/{filename}"

PRODUCTS_DATA = [
    # ── APPLE ──
    {
        "category": "هواتف ذكية",
        "brand": "Apple",
        "type": "phone",
        "name": "Apple iPhone 17 Pro Max",
        "description": "هاتف آبل الرائد الجديد مع معالج فائق القوة، كاميرات احترافية، وشاشة Super Retina XDR متطورة. نسخة أصلية غير مفعّلة (No Active).",
        "is_featured": True,
        "variants": [
            {"name": "256GB / 1SIM / F/A No Active", "price": 1280.00}
        ]
    },

    # ── SAMSUNG ──
    {
        "category": "هواتف ذكية",
        "brand": "Samsung",
        "type": "phone",
        "name": "Samsung Galaxy A07",
        "description": "هاتف سامسونج جالاكسي A07 الاقتصادي بشاشة عريضة وبطارية تدوم طويلاً، كفالة وضمان رسمي معتمد.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB (بدون شاحن)", "price": 122.00},
            {"name": "RAM 4GB / 128GB (بدون شاحن)", "price": 133.00},
            {"name": "RAM 6GB / 128GB (مع شاحن)", "price": 163.00},
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Samsung",
        "type": "phone",
        "name": "Samsung Galaxy A17",
        "description": "هاتف سامسونج جالاكسي A17 بتصميم أنيق وأداء متوازن، كاميرا متعددة العدسات وسرعة استجابة ممتازة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 253.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Samsung",
        "type": "phone",
        "name": "Samsung Galaxy A37",
        "description": "هاتف سامسونج جالاكسي A37 بشاشة Super AMOLED متطورة وذاكرة 12 جيجابايت لتجربة استخدام فائقة السرعة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 12GB / 256GB", "price": 375.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Samsung",
        "type": "phone",
        "name": "Samsung Galaxy A57",
        "description": "سامسونج جالاكسي A57 الأقوى في الفئة المتوسطة، مقاوم للماء والغبار وكاميرا بدقة فائقة مع تثبيت بصري.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 405.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Samsung",
        "type": "phone",
        "name": "Samsung Galaxy S26 Ultra",
        "description": "الهاتف الرائد الأقوى من سامسونج مع قلم S-Pen مدمج، شاشة ديناميكية فائقة الدقة وكاميرا زووم خارقة وأداء ذكاء اصطناعي متقدم.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 256GB", "price": 925.00}
        ]
    },
    {
        "category": "شواحن وإكسسوارات",
        "brand": "Samsung",
        "type": "charger",
        "name": "شاحن سامسونج 45W أصلي كامل",
        "description": "رأس شاحن سامسونج سريع بقوة 45 واط الأصلي مع كابل شحن فائق السرعة، متوافق مع كافة أجهزة جالاكسي والهواتف الحديثة.",
        "is_featured": True,
        "variants": [
            {"name": "شاحن كامل 45 واط أصلي مع كابل", "price": 15.00}
        ]
    },
    {
        "category": "راوترات وشبكات",
        "brand": "Huawei / Generic",
        "type": "router",
        "name": "راوتر B315 4G LTE منزلي ومكتبي",
        "description": "راوتر شبكات B315 يدعم شريحة 4G LTE لتوزيع الإنترنت المنزلي والمكتبي بكفاءة وسرعة اتصال مستقرة.",
        "is_featured": True,
        "variants": [
            {"name": "راوتر B315 4G صيني", "price": 8.00}
        ]
    },

    # ── XIAOMI ──
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Xiaomi",
        "type": "tablet",
        "name": "Xiaomi Pad 2",
        "description": "تابلت شاومي باد 2 بشاشة عالية الدقة وسماعات ستيريو محيطية، مثالي للدراسة والعمل والترفيه، يأتي مع كفر حماية مجاني.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 4GB / 128GB Global (مع كفر)", "price": 175.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi A5",
        "description": "هاتف ريدمي A5 الاقتصادي بتصميم عصري وخفيف الوزن وبطارية ضخمة 5000 مللي أمبير بنسخة عالمية رسمية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 3GB / 64GB Global", "price": 102.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi A7 Pro",
        "description": "هاتف ريدمي A7 برو بشاشة عالية السطوع ومعالج موفر للطاقة مع أداء سلس، كفالة استبدال لأي عطل مصنعي.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB Global", "price": 107.00},
            {"name": "RAM 4GB / 128GB Global 💯", "price": 124.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi 15 4G",
        "description": "هاتف ريدمي 15 الجيل الرابع بتصميم زجاجي أنيق وكاميرا متطورة وشحن سريع، نسخة عالمية معتمدة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB Global", "price": 158.00},
            {"name": "RAM 8GB / 256GB Global", "price": 198.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi 17 4G",
        "description": "هاتف ريدمي 17 الجيل الرابع بمواصفات مطورة وشاشة بمعدل تحديث سلس وتجربة ألعاب ممتعة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 128GB Global", "price": 151.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 14 5G",
        "description": "ريدمي نوت 14 يدعم شبكات الجيل الخامس 5G مع شاشة أموليد وكاميرا فائقة الوضوح، نسخة هندية أصلية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB IND 🇮🇳", "price": 210.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 14S",
        "description": "ريدمي نوت 14S بأداء قوي وسرعة استجابة مذهلة في التطبيقات والألعاب وبطارية تدوم طويلاً.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB Global", "price": 223.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 14 Pro Plus",
        "description": "ريدمي نوت 14 برو بلس بكاميرا احترافية بدقة 200 ميجابكسل وشحن فائق السرعة، نسخة أصلية معتمدة.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 128GB IND 🇮🇳", "price": 278.00},
            {"name": "RAM 8GB / 256GB IND 🇮🇳", "price": 295.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 15",
        "description": "ريدمي نوت 15 الجيل الجديد، توازن مثالي بين الأداء، البطارية، ودقة الشاشة وسرعة التصفح.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB Global", "price": 204.00},
            {"name": "RAM 8GB / 256GB Global 4G", "price": 233.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 15 Pro",
        "description": "ريدمي نوت 15 برو بشاشة فائقة النقاء وحماية متقدمة للعين ونظام تصوير ليلي سينمائي.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB 4G Global", "price": 295.00},
            {"name": "RAM 8GB / 256GB 5G Global", "price": 302.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 15 Pro Plus",
        "description": "النسخة الأقوى ريدمي نوت 15 برو بلس بسعة 512 جيجابايت وذاكرة عشوائية 12 جيجابايت، جهاز مختوم وجاهز للتسليم.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 512GB Global مختوم", "price": 404.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 17",
        "description": "ريدمي نوت 17 الأحدث كلياً بتقنيات حديثة وتصميم ألترا سليم.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB Global", "price": 209.00},
            {"name": "RAM 8GB / 256GB Global", "price": 237.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 17 Pro 5G",
        "description": "ريدمي نوت 17 برو 5G معالج قوي، كاميرات مذهلة، وشاشة بمعدل 144 هرتز.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 12GB / 256GB 5G Global", "price": 345.00},
            {"name": "RAM 8GB / 512GB 5G Global", "price": 385.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Redmi Note 17 Pro Max",
        "description": "ريدمي نوت 17 برو ماكس، شاشة عملاقة وبطارية تدوم أياماً مع قدرات تصوير خارقة.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 512GB Global", "price": 455.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Xiaomi",
        "type": "phone",
        "name": "Xiaomi Mi 15 Ultra",
        "description": "الهاتف الرائد الخارق من شاومي Mi 15 ألترا بكاميرات لايكا الأسطورية، وسعة 1 تيرابايت وذاكرة 16 جيجابايت.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 16GB / 1TB Global", "price": 1080.00}
        ]
    },

    # ── POCO ──
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Poco",
        "type": "tablet",
        "name": "Poco Pad C1",
        "description": "تابلت بوكو C1 للألعاب والعمل، شاشة مريحة للعين ومعالج قوي وبطارية تدعم الشحن السريع.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB", "price": 163.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco C71",
        "description": "هاتف بوكو C71 الاقتصادي بشاشة عريضة وأداء سريع للمهام اليومية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 3GB / 64GB Global", "price": 104.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco C81 Pro",
        "description": "هاتف بوكو C81 برو بنسخة عالمية وذاكرة 128 جيجابايت، تصميم أنيق وجذاب.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 128GB Global", "price": 123.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco C85",
        "description": "هاتف بوكو C85 بذاكرة عشوائية 6 جيجابايت لأداء سلس في التصفح والتطبيقات.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB Global (بدون شاحن)", "price": 137.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco C95 Pro",
        "description": "هاتف بوكو C95 برو بسعة 256 جيجابايت وذاكرة 8 جيجابايت، شاشة ديناميكية سريعة الاستجابة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB Global", "price": 218.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco M7",
        "description": "هاتف بوكو M7 المتميز في فئته ببطارية ضخمة ومعالج ألعاب متوازن وتصميم جريء.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB Global", "price": 149.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco X6 Pro",
        "description": "وحش الألعاب بوكو X6 برو، معالج رائد Dimensity 8300-Ultra، شاشة CrystalRes AMOLED، وسعة 512 جيجابايت.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 512GB Global", "price": 319.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco X8",
        "description": "هاتف بوكو X8 الجيل الجديد للألعاب والسرعة مع تبريد مائي وسماعات مزدوجة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB Global", "price": 300.00},
            {"name": "RAM 12GB / 256GB Global", "price": 327.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Poco",
        "type": "phone",
        "name": "Poco F9 Pro",
        "description": "فلاجشيب بوكو F9 برو للأداء الخارق وسرعة معالجة الرسوميات بسعة 512 جيجابايت و12 جيجابايت رام.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 512GB Global", "price": 680.00}
        ]
    },

    # ── INFINIX ──
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Smart 20",
        "description": "هاتف إنفينيكس سمارت 20 الاقتصادي والعملي، ضمان أرابيا مع كفالة استبدال 30 يوماً.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB", "price": 125.00},
            {"name": "RAM 4GB / 128GB", "price": 145.00},
            {"name": "RAM 4GB / 256GB", "price": 165.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Hot 70",
        "description": "هاتف إنفينيكس هوت 70، تصميم أنيق وشاشة عريضة مع تجربة صوتية نقية وكاميرات بدقة عالية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 256GB", "price": 235.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Hot 70 Pro 5G",
        "description": "إنفينيكس هوت 70 برو 5G يدعم شبكات الجيل الخامس بسرعة فائقة وشحن سريع متطور.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 256GB 5G", "price": 325.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix GT 50 Pro",
        "description": "هاتف الألعاب المستقبلي إنفينيكس GT 50 برو بإضاءة خلفية تفاعلية، معالج ألعاب قوي ويأتي مع بكج متكامل.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 256GB (مع بكج)", "price": 475.00},
            {"name": "RAM 12GB / 512GB (مع بكج)", "price": 525.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Note 60",
        "description": "إنفينيكس نوت 60 المخصص للمحترفين مع شاشة منحنية AMOLED وشحن لاسلكي سريع.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 359.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Note 60 Pro",
        "description": "إنفينيكس نوت 60 برو، كاميرا فائقة الثبات وتصميم فخم بملمس جلدي ونظام صوتي JBL.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 389.00},
            {"name": "RAM 12GB / 256GB", "price": 450.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Infinix",
        "type": "phone",
        "name": "Infinix Note 60 Ultra",
        "description": "إنفينيكس نوت 60 ألترا، القمة في سلسلة نوت بمواصفات حصرية وقدرات ذكاء اصطناعي متقدمة.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 256GB", "price": 650.00}
        ]
    },
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Infinix",
        "type": "tablet",
        "name": "Infinix X Pad 30E",
        "description": "تابلت إنفينيكس X باد 30E يدعم تركيب شريحة اتصال SIM، مناسب للدراسة والمكالمات والتطبيقات المكتبية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 128GB SIM", "price": 150.00},
            {"name": "RAM 8GB / 256GB SIM", "price": 245.00}
        ]
    },

    # ── HONOR ──
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor T10",
        "description": "هاتف هونر T10 الاقتصادي والعملي، كفالة معتمدة وضمان جودة هونر الأصلية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 3GB / 32GB", "price": 85.00},
            {"name": "RAM 4GB / 64GB", "price": 96.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor Play 20C",
        "description": "هونر بلاي 20C بشاشة عريضة ونظام أندرويد سريع وتصميم مريح لليد.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB", "price": 109.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor X9D",
        "description": "هونر X9D الشاشة غير القابلة للكسر مع بطارية عملاقة وكاميرا بدقة 108 ميجابكسل.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 339.00},
            {"name": "RAM 12GB / 256GB", "price": 369.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor X7E",
        "description": "هونر X7E بتصميم خفيف وأنيق وبطارية تدوم ليومين مع شاحن هونر السريع.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 256GB", "price": 215.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor X7E Plus",
        "description": "هونر X7E بلس بمواصفات إضافية ومساحة تخزين 256 جيجابايت.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 256GB", "price": 255.00},
            {"name": "RAM 8GB / 256GB 5G", "price": 269.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor 600 Lite",
        "description": "هونر 600 لايت بتصميم رائد ونحيف جداً، شاشة أموليد حماية للعين وكاميرا سيلفي متميزة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 128GB", "price": 259.00},
            {"name": "RAM 8GB / 256GB", "price": 289.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor 600",
        "description": "هونر 600 الفئة الراقية، قدرات تصوير بورتريه سينمائية وشحن فائق السرعة.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 449.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor Magic 8 Pro",
        "description": "فلاجشيب هونر ماجيك 8 برو بمواصفات خارقة: رام 16 جيجابايت وسعة 1 تيرابايت، مقاوم للماء IP68 وأقوى معالج رائد.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 16GB / 1TB", "price": 999.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Honor",
        "type": "phone",
        "name": "Honor Magic V6",
        "description": "تحفة هونر القابلة للطي ماجيك V6، أنحف هاتف فولد في العالم مع شاشتين مذهلتين وهدايا حصرية 🎁.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 16GB / 512GB (هدايا حصرية)", "price": 1599.00}
        ]
    },
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Honor",
        "type": "tablet",
        "name": "Honor Pad X8B",
        "description": "تابلت هونر X8B بتصميم معدني أنيق وشاشة مريحة للقراءة وسماعات رباعية نقية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB", "price": 159.00},
            {"name": "RAM 4GB / 128GB", "price": 175.00}
        ]
    },
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Honor",
        "type": "tablet",
        "name": "Honor Magic Pad 3",
        "description": "تابلت هونر الاحترافي ماجيك باد 3 بسعة 512 جيجابايت ورام 16 جيجابايت، شاشة 3K لإنتاج المحتوى والعمل المكتبي الاحترافي.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 16GB / 512GB", "price": 729.00}
        ]
    },

    # ── TECNO ──
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Pop 20C",
        "description": "هاتف تكنو بوب 20C الاقتصادي بشاشة عريضة ومكبر صوت مزدوج وبطارية طويلة العمر.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB", "price": 117.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Spark Go 3",
        "description": "هاتف تكنو سبارك جو 3 الاقتصادي بتصميم أنيق ومقاوم لقطرات الماء.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 64GB", "price": 124.00},
            {"name": "RAM 4GB / 128GB", "price": 139.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Spark 50",
        "description": "هاتف تكنو سبارك 50 بشاشة بمعدل تحديث 90 هرتز وسعة تخزين ضخمة 256 جيجابايت.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 256GB", "price": 179.00},
            {"name": "RAM 6GB / 256GB", "price": 235.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Pova Slim",
        "description": "هاتف تكنو بوفا سليم فائق النحافة مع بطارية ضخمة ومعالج ألعاب متوازن.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 8GB / 256GB", "price": 245.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Pova Curve 2",
        "description": "تكنو بوفا كيرف 2 بشاشة منحنية جذابة وتصميم مستقبلي، يأتي مع بكج متكامل.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 256GB (مع بكج)", "price": 335.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Camon 50 Pro",
        "description": "تكنو كامون 50 برو المتخصص في التصوير الليلي والبورتريه مع مستشعر سوني متطور وبكج هدايا.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 8GB / 256GB (مع بكج)", "price": 359.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Tecno",
        "type": "phone",
        "name": "Tecno Camon 50 Ultra",
        "description": "فلاجشيب تكنو كامون 50 ألترا بقدرات تصوير سينمائي ورام 12 جيجابايت وبكج هدايا متكامل.",
        "is_featured": True,
        "variants": [
            {"name": "RAM 12GB / 256GB (مع بكج)", "price": 455.00}
        ]
    },
    {
        "category": "أجهزة لوحية (تابلت)",
        "brand": "Tecno",
        "type": "tablet",
        "name": "Tecno Pad SE",
        "description": "تابلت تكنو باد SE بشاشة مريحة للعين واتصال واي فاي سريع وسماعات ستيريو محيطية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 128GB WiFi", "price": 155.00}
        ]
    },

    # ── ITEL ──
    {
        "category": "هواتف ذكية",
        "brand": "Itel",
        "type": "phone",
        "name": "Itel A100CS",
        "description": "هاتف آيتيل A100CS الاقتصادي الممتاز للاستخدام الأساسي والمكالمات والتطبيقات اليومية مع كفالة استبدال 30 يوماً.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 2GB / 64GB", "price": 77.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Itel",
        "type": "phone",
        "name": "Itel A200",
        "description": "هاتف آيتيل A200 بشاشة عريضة وتصميم مريح وكفالة استبدال معتمدة.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 3GB / 64GB", "price": 89.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Itel",
        "type": "phone",
        "name": "Itel City 200S",
        "description": "هاتف آيتيل سيتي 200S بذاكرة 128 جيجابايت ورام 4 جيجابايت، أداء موثوق وسعر تنافسي.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 4GB / 128GB", "price": 115.00}
        ]
    },

    # ── MODIO ──
    {
        "category": "هواتف ذكية",
        "brand": "Modio",
        "type": "phone",
        "name": "Modio H18 Pro Max",
        "description": "هاتف ميديو H18 برو ماكس بسعة 256 جيجابايت ورام 12 جيجابايت وبطارية قوية وسعر اقتصادي جداً.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 12GB / 256GB", "price": 69.00}
        ]
    },

    # ── ZTE ──
    {
        "category": "هواتف ذكية",
        "brand": "ZTE",
        "type": "phone",
        "name": "ZTE A35E",
        "description": "هاتف زد تي إي A35E الاقتصادي الصغير والعملي ببطارية تدوم طويلاً وسعر اقتصادي.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 2GB / 64GB", "price": 78.00}
        ]
    },

    # ── SUMAX ──
    {
        "category": "هواتف ذكية",
        "brand": "Sumax",
        "type": "phone",
        "name": "Sumax 18 Pro Max",
        "description": "هاتف سوماكس 18 برو ماكس (كوبي صيني) بمظهر عصري وسعة 1 تيرابايت ورام 12 جيجابايت.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 12GB / 1TB (كوبي صيني)", "price": 59.00}
        ]
    },

    # ── REEKOO ──
    {
        "category": "هواتف ذكية",
        "brand": "Reekoo",
        "type": "phone",
        "name": "Reekoo Magic 70",
        "description": "هاتف ريكو ماجيك 70 الاقتصادي والأنيق، شاشة واضحة وتصميم مميز.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 3GB / 64GB", "price": 85.00}
        ]
    },
    {
        "category": "هواتف ذكية",
        "brand": "Reekoo",
        "type": "phone",
        "name": "Reekoo 17 Pro Max",
        "description": "هاتف ريكو 17 برو ماكس بذاكرة 128 جيجابايت ورام 6 جيجابايت، ويأتي مع سماعة أذن مجانية.",
        "is_featured": False,
        "variants": [
            {"name": "RAM 6GB / 128GB (مع سماعة)", "price": 115.00}
        ]
    }
]



class Command(BaseCommand):
    help = "Seeds all authentic physical tech products with variants and studio images."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">> Seeding official hardware devices catalog..."))
        
        # Deactivate digital products
        d_count = Product.all_objects.filter(product_type='digital').update(is_active=False, is_publicly_visible=False)
        self.stdout.write(f"Deactivated {d_count} digital products.")

        with bypass_tenant_filter():
            cat_map = {}
            for item in PRODUCTS_DATA:
                cat_name = item["category"]
                if cat_name not in cat_map:
                    cat_obj, _ = Category.objects.get_or_create(
                        name=cat_name,
                        defaults={"is_active": True, "is_publicly_visible": True, "compliance_status": "compliant"}
                    )
                    cat_obj.is_active = True
                    cat_obj.is_publicly_visible = True
                    cat_obj.save()
                    cat_map[cat_name] = cat_obj

            created_count = 0
            updated_count = 0
            variant_count = 0

            for item in PRODUCTS_DATA:
                cat_obj = cat_map[item["category"]]
                filename = f"{slugify(item['name'])}.jpg"
                img_rel_path = generate_device_image(filename, item["brand"], item["name"], item["type"])

                prod, created = Product.objects.get_or_create(
                    name=item["name"],
                    defaults={
                        "category": cat_obj,
                        "product_type": "physical",
                        "image": img_rel_path,
                        "description": item["description"],
                        "is_active": True,
                        "is_featured": item["is_featured"],
                        "is_publicly_visible": True,
                        "compliance_status": "compliant",
                    }
                )

                if not created:
                    prod.category = cat_obj
                    prod.product_type = "physical"
                    prod.image = img_rel_path
                    prod.description = item["description"]
                    prod.is_active = True
                    prod.is_featured = item["is_featured"]
                    prod.is_publicly_visible = True
                    prod.compliance_status = "compliant"
                    prod.save()
                    updated_count += 1
                else:
                    created_count += 1

                for v_idx, v_data in enumerate(item["variants"], 1):
                    v_name = v_data["name"]
                    v_price = Decimal(str(v_data["price"]))

                    var_obj = ProductVariant.objects.filter(product=prod, name=v_name).first()
                    if not var_obj:
                        clean_name = re.sub(r'[^a-zA-Z0-9]', '', item["name"])[:10].upper() or "PROD"
                        clean_v = re.sub(r'[^a-zA-Z0-9]', '', v_name)[:6].upper() or "VAR"
                        base_sku = f"{clean_name}-{clean_v}-{v_idx}"
                        sku = base_sku
                        counter = 1
                        while ProductVariant.objects.filter(sku=sku).exists():
                            sku = f"{base_sku}-{counter}"
                            counter += 1

                        var_obj = ProductVariant.objects.create(
                            product=prod,
                            name=v_name,
                            sku=sku,
                            price=v_price,
                            cost=Decimal("0.00"),
                            wholesale_price=v_price,
                            vip_price=v_price,
                            is_active=True
                        )
                    else:
                        var_obj.price = v_price
                        var_obj.is_active = True
                        if not var_obj.sku:
                            var_obj.sku = f"SKU-{prod.id}-{var_obj.id}-{uuid.uuid4().hex[:6]}".upper()
                        var_obj.save()
                    variant_count += 1

        self.stdout.write(self.style.SUCCESS(f">> Finished! Synced {created_count + updated_count} products and {variant_count} variants."))
