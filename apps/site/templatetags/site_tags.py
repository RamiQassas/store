from django import template
from decimal import Decimal
from apps.common.models import Currency

register = template.Library()

@register.filter
def convert_price(amount, target_currency):
    """
    Converts an amount from the base currency (usually USD or what's defined as base) 
    to the target currency.
    Note: The project seems to use SYP as a base in many places or SYP is just hardcoded.
    Looking at Currency model, 'to_base' and 'from_base' use SYP-like rates.
    If 1 USD = 10500 SYP, then SYP is the 'base' in terms of the rate definition.
    """
    if not amount or not target_currency:
        return amount
        
    try:
        # Assume amount is in the platform's default/base currency.
        # Based on existing code, prices in models are often treated as 'base' values.
        # We'll use 'from_base' logic.
        converted = target_currency.from_base(amount)
        
        # Format based on decimal places
        return f"{converted:,.{target_currency.decimal_places}f}"
    except Exception:
        return amount

@register.simple_tag(takes_context=True)
def variant_price(context, variant):
    """
    Returns the price of a variant for the current user in context.
    """
    if variant is None:
        return None

    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return variant.price
    
    return variant.get_price_for_user(request.user)

@register.simple_tag(takes_context=True)
def variant_card_price(context, variant):
    """
    Returns the formatted starting/display price for a variant card.
    For range/per-mille products with a min quantity (e.g. 100), calculates the starting price.
    """
    if variant is None:
        return ""
    
    price = variant_price(context, variant)
    if not price:
        return currency_format(context, 0)
    
    meta = variant.metadata or {}
    qty_type = meta.get("qty_type")
    qty_min = meta.get("qty_min")
    qty_list = meta.get("qty_list", [])
    is_per_mille = meta.get("is_per_mille", False)
    
    min_multiplier = Decimal("1")
    try:
        if qty_min:
            q_val = Decimal(str(qty_min))
            if q_val > 1:
                min_multiplier = q_val
    except Exception:
        pass
        
    if qty_list:
        try:
            valid_list = [Decimal(str(x)) for x in qty_list if Decimal(str(x)) > 0]
            if valid_list:
                min_in_list = min(valid_list)
                if min_in_list > 1 and (is_per_mille or Decimal(str(price)) < Decimal("0.2") or qty_type in ("list", "range", "custom_qty")):
                    if min_multiplier == 1 or min_in_list < min_multiplier:
                        min_multiplier = min_in_list
        except Exception:
            pass
            
    if min_multiplier > 1:
        total = Decimal(str(price)) * min_multiplier
        formatted = currency_format(context, total)
        return f"{formatted} <span class='text-[10px] text-slate-400 block font-normal'>(تبدأ من {int(min_multiplier)})</span>"
    
    return currency_format(context, price)

@register.simple_tag(takes_context=True)
def product_starting_price(context, product):
    """
    Returns the starting minimum price for a product card across active variants.
    Calculates the true starting cost by factoring in qty_min and qty_list for range/per-mille products.
    """
    if not product:
        return ""
        
    try:
        variants = product.variants.all()
    except Exception:
        variants = []
        
    lowest_price = None
    
    for v in variants:
        # Skip inactive or corrupt/null variants
        if getattr(v, 'is_active', True) is False:
            continue
        v_name = (v.name or "").lower()
        if "(#" in v.name or "null" in v_name:
            continue
            
        v_price = variant_price(context, v)
        if v_price is None:
            continue
            
        meta = v.metadata or {}
        qty_type = meta.get("qty_type")
        qty_min = meta.get("qty_min")
        qty_list = meta.get("qty_list", [])
        is_per_mille = meta.get("is_per_mille", False)
        
        min_multiplier = Decimal("1")
        try:
            if qty_min:
                q_val = Decimal(str(qty_min))
                if q_val > 1:
                    min_multiplier = q_val
        except Exception:
            pass
            
        if qty_list:
            try:
                valid_list = [Decimal(str(x)) for x in qty_list if Decimal(str(x)) > 0]
                if valid_list:
                    min_in_list = min(valid_list)
                    if min_in_list > 1 and (is_per_mille or Decimal(str(v_price)) < Decimal("0.2") or qty_type in ("list", "range", "custom_qty")):
                        if min_multiplier == 1 or min_in_list < min_multiplier:
                            min_multiplier = min_in_list
            except Exception:
                pass

        total = Decimal(str(v_price)) * min_multiplier
            
        if lowest_price is None or total < lowest_price:
            lowest_price = total
            
    if lowest_price is None:
        p_price = getattr(product, 'price', 0) or 0
        try:
            lowest_price = Decimal(str(p_price))
        except Exception:
            lowest_price = Decimal("0")
            
    return currency_format(context, lowest_price)

@register.filter
def to_usd(amount, currency):
    """Converts an amount in the given currency to USD."""
    if not amount or not currency:
        return Decimal("0.00")
    try:
        return currency.to_base(amount, "deposit")
    except:
        return Decimal("0.00")

@register.simple_tag(takes_context=True)
def currency_format(context, amount, source_currency=None, mode="deposit"):
    """
    Formats a price according to the current preferred currency in context.
    If source_currency is provided, it converts from it to preferred.
    Otherwise, assumes amount is in source_currency.code or USD.
    """
    target_currency = context.get('CURRENCY')
    system_currency = context.get('SYSTEM_CURRENCY') # Usually USD

    if amount is None:
        return "غير متوفر"
    
    try:
        val = Decimal(str(amount))
        source = source_currency or system_currency
        
        # If no target, fallback to original or system
        if not target_currency:
            symbol = source.symbol if source else "USD"
            places = source.decimal_places if source else 2
            return f"{val:,.{places}f} {symbol}"

        # 1. Convert source to BASE (USD)
        base_amount = val
        if source and source.code != "USD":
            base_amount = source.to_base(val, operation=mode)
        
        # 2. Convert BASE to target
        converted = target_currency.from_base(base_amount, operation=mode)
        
        prefix = ""
        # Only show approx if target is not USD and it's a conversion result
        if target_currency.code != "USD" and source and source.code != target_currency.code:
            prefix = "≈ "
            
        places = target_currency.decimal_places
        if converted > 0 and converted < Decimal("0.01"):
            places = 4
        if converted > 0 and converted < Decimal("0.0001"):
            places = 6

        formatted = f"{converted:,.{places}f}"
        return f"{prefix}{formatted} {target_currency.symbol}"
    except Exception:
        return f"{amount} {target_currency.symbol if target_currency else '???'}"

@register.filter
def subtract(value, arg):
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except:
        return 0

@register.filter
def mul(value, arg):
    """Multiplies the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """Divides the value by the argument."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def trim(value):
    if not isinstance(value, str):
        return value
    return value.strip()

@register.filter
def is_list(value):
    return isinstance(value, list)

@register.filter
def replace(value, args):
    if len(args.split(',')) != 2:
        return value
    old, new = args.split(',')
    return value.replace(old, new)

@register.filter(name='add_class')
def add_class(value, arg):
    """Adds a CSS class to a form field widget."""
    try:
        return value.as_widget(attrs={'class': arg})
    except:
        return value

@register.filter
def get_item(dictionary, key):
    """Returns the value for a given key in a dictionary."""
    if not dictionary:
        return None
    return dictionary.get(str(key)) or dictionary.get(key)

from django.utils.safestring import mark_safe

@register.simple_tag
def get_deposit_config(payment_method, user):
    try:
        return mark_safe(payment_method.to_deposit_json(user=user))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in get_deposit_config: {e}", exc_info=True)
        return "{}"

@register.simple_tag
def get_withdrawal_config(payment_method, user):
    try:
        return mark_safe(payment_method.to_withdrawal_json(user=user))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in get_withdrawal_config: {e}", exc_info=True)
        return "{}"


@register.filter
def translate_ledger_source(source):
    translation_map = {
        "p2p transfer out": "تحويل مالي مرسل (P2P)",
        "p2p transfer in": "تحويل مالي مستلم (P2P)",
        "p2p reversal out": "إلغاء وإرجاع تحويل مرسل",
        "p2p reversal in": "إلغاء وإرجاع تحويل مستلم",
        "recharge_card": "شحن بطاقة رصيد",
        "deposit": "عملية إيداع",
        "withdrawal": "عملية سحب",
        "order": "شراء خدمة/منتج",
        "admin_adjustment": "تعديل رصيد إداري",
        "admin_cash": "سداد نقدي إداري",
        "admin": "تعديل إداري",
        "system": "عملية للنظام"
    }
    if not source:
        return ""
    src_lower = str(source).strip().lower()
    return translation_map.get(src_lower, source)


@register.filter
def getattr_filter(obj, attr_name):
    """Dynamically get an attribute of an object in a template."""
    if not obj:
        return None
    return getattr(obj, attr_name, None)


@register.filter
def is_location_url(value):
    if not isinstance(value, str):
        return False
    value_lower = value.strip().lower()
    return (
        value_lower.startswith("http://") or 
        value_lower.startswith("https://") or 
        "maps.google" in value_lower or 
        "google.com/maps" in value_lower or 
        "maps.app.goo.gl" in value_lower
    )


import json

@register.filter
def jsonify(val):
    if val is None:
        return "[]"
    try:
        return mark_safe(json.dumps(val, ensure_ascii=False))
    except Exception:
        return "[]"

@register.filter
def is_list(val):
    return isinstance(val, (list, tuple))

@register.filter
def as_list(val):
    if isinstance(val, (list, tuple)):
        return val
    if isinstance(val, str):
        if "\n" in val:
            return [x.strip() for x in val.split("\n") if x.strip()]
        if " | " in val:
            return [x.strip() for x in val.split(" | ") if x.strip()]
        if "," in val:
            return [x.strip() for x in val.split(",") if x.strip()]
    if val is not None and val != "":
        return [val]
    return []


@register.filter
def is_image_url(val):
    if not isinstance(val, str):
        return False
    val_clean = val.strip().lower()
    return val_clean.startswith("http") and any(ext in val_clean for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", "/avatar/"])


@register.filter
def clean_fulfillment_items(fulfillment):
    """
    Returns a list of (key, cleaned_value) tuples for rendering to customers,
    filtering out internal API keys, raw json/dict structures, and suppressing duplicates.
    """
    if not fulfillment or not isinstance(fulfillment, dict):
        return []
        
    from apps.orders.provider_status import extract_clean_text

    ignored_keys = {
        "api_provider", "api_status", "api_last_response", 
        "api_refunded", "response", "api_response", 
        "api_error", "alkasr", "api_order_id",
        "ملاحظات وبيانات التنفيذ", "image_url"
    }

    delivery_val = extract_clean_text(fulfillment.get("بيانات التسليم والأكواد") or fulfillment.get("keys") or fulfillment.get("كود التفعيل / البطاقة"))
    cancel_val = extract_clean_text(fulfillment.get("سبب الإلغاء من السيرفر"))
    server_msg = extract_clean_text(fulfillment.get("رد السيرفر"))
    avatar_val = fulfillment.get("صورة الحساب / الأفاتار") or fulfillment.get("image_url")

    result = []
    seen_values = set()

    # 1. Delivery codes / keys (Highest priority for customer)
    for deliv_key in ("بيانات التسليم والأكواد", "keys", "كود التفعيل / البطاقة", "رقم الهاتف المستلم"):
        if deliv_key in fulfillment:
            c_val = extract_clean_text(fulfillment[deliv_key])
            if c_val and c_val not in seen_values:
                result.append((deliv_key, c_val))
                seen_values.add(c_val)

    # 2. Account info / Avatar
    if avatar_val and str(avatar_val).strip() not in seen_values:
        result.append(("صورة الحساب / الأفاتار", str(avatar_val).strip()))
        seen_values.add(str(avatar_val).strip())

    for acc_key in ("اسم الحساب المستلم", "حالة العملية", "الباقة المنفذة"):
        if acc_key in fulfillment:
            c_val = extract_clean_text(fulfillment[acc_key])
            if c_val and c_val not in seen_values:
                result.append((acc_key, c_val))
                seen_values.add(c_val)

    # 3. Cancellation reason (High priority if cancelled)
    if cancel_val and cancel_val not in seen_values:
        result.append(("سبب الإلغاء من السيرفر", cancel_val))
        seen_values.add(cancel_val)

    # 4. Server reply / replies
    multi_responses = fulfillment.get("all_server_responses") or fulfillment.get("ردود السيرفر")
    if isinstance(multi_responses, list) and len(multi_responses) > 1:
        for idx, r_msg in enumerate(multi_responses, 1):
            r_clean = extract_clean_text(r_msg)
            if r_clean and r_clean not in seen_values:
                result.append((f"رد السيرفر ({idx})", r_clean))
                seen_values.add(r_clean)
    elif server_msg and server_msg not in seen_values:
        result.append(("رد السيرفر", server_msg))
        seen_values.add(server_msg)

    # 5. Any other remaining custom keys
    for k, v in fulfillment.items():
        if k in ignored_keys or any(k == r[0] for r in result):
            continue
        c_val = extract_clean_text(v)
        if c_val and c_val not in seen_values:
            result.append((k, c_val))
            seen_values.add(c_val)

    return result


@register.filter
def tenant_title(raw_title, store_name=None):
    """
    Replaces static 'رقميات' or 'Raqamiyat' references in page titles
    with the current tenant store's name.
    """
    if not store_name:
        try:
            from apps.common.tenant_utils import get_current_store
            store = get_current_store()
            if store and hasattr(store, "name") and store.name:
                store_name = store.name
        except Exception:
            pass

    if not raw_title:
        return store_name or "رقميات"
    
    if not store_name or store_name.strip() in ["رقميات", "Raqamiyat"]:
        return raw_title

    t = str(raw_title).strip()
    replacements = [
        ("رقميات | كل ما تحتاجه من خدمات رقمية في مكان واحد", store_name),
        ("Raqamiyat | رقميات", store_name),
        ("رقميات - Raqamiyat", store_name),
        ("Raqamiyat Admin", f"{store_name} Admin"),
        ("Raqamiyat Elite", store_name),
        ("Raqamiyat Control", store_name),
        ("Raqamiyat Builder", store_name),
        ("رقميات SaaS", store_name),
        ("Raqamiyat", store_name),
        ("رقميات", store_name),
    ]
    for old, new in replacements:
        if old in t:
            t = t.replace(old, new)
    return t


BRAND_LOGOS_MAP = {
    "pubg": "https://upload.wikimedia.org/wikipedia/en/thumb/5/52/PUBG_Mobile_logo.png/320px-PUBG_Mobile_logo.png",
    "free fire": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Garena_Free_Fire_Logo.png/320px-Garena_Free_Fire_Logo.png",
    "فايتر": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Garena_Free_Fire_Logo.png/320px-Garena_Free_Fire_Logo.png",
    "roblox": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Roblox_player_icon_black.svg/320px-Roblox_player_icon_black.svg.png",
    "روبلوكس": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Roblox_player_icon_black.svg/320px-Roblox_player_icon_black.svg.png",
    "roblex": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Roblox_player_icon_black.svg/320px-Roblox_player_icon_black.svg.png",
    "jawaker": "https://images.seeklogo.com/logo-png/43/1/jawaker-logo-png_seeklogo-435552.png",
    "جواكر": "https://images.seeklogo.com/logo-png/43/1/jawaker-logo-png_seeklogo-435552.png",
    "tiktok": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a9/TikTok_logo.svg/320px-TikTok_logo.svg.png",
    "تيك توك": "https://upload.wikimedia.org/wikipedia/en/thumb/a/a9/TikTok_logo.svg/320px-TikTok_logo.svg.png",
    "netflix": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/320px-Netflix_2015_logo.svg.png",
    "نتفلكس": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/320px-Netflix_2015_logo.svg.png",
    "shahid": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Shahid_VIP_logo.svg/320px-Shahid_VIP_logo.svg.png",
    "شاهد": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Shahid_VIP_logo.svg/320px-Shahid_VIP_logo.svg.png",
    "telegram": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Telegram_logo.svg/320px-Telegram_logo.svg.png",
    "تيليجرام": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Telegram_logo.svg/320px-Telegram_logo.svg.png",
    "google play": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Google_Play_Arrow_logo.svg/320px-Google_Play_Arrow_logo.svg.png",
    "جوجل بلاي": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Google_Play_Arrow_logo.svg/320px-Google_Play_Arrow_logo.svg.png",
    "itunes": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/ITunes_logo.svg/320px-ITunes_logo.svg.png",
    "apple": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/Apple_logo_black.svg/320px-Apple_logo_black.svg.png",
    "ايتونز": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/ITunes_logo.svg/320px-ITunes_logo.svg.png",
    "steam": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/320px-Steam_icon_logo.svg.png",
    "ستيم": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/320px-Steam_icon_logo.svg.png",
    "playstation": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/PlayStation_logo.svg/320px-PlayStation_logo.svg.png",
    "بلايستيشن": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/PlayStation_logo.svg/320px-PlayStation_logo.svg.png",
    "psn": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/PlayStation_logo.svg/320px-PlayStation_logo.svg.png",
    "xbox": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Xbox_one_logo.svg/320px-Xbox_one_logo.svg.png",
    "اكس بوكس": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Xbox_one_logo.svg/320px-Xbox_one_logo.svg.png",
    "discord": "https://upload.wikimedia.org/wikipedia/en/thumb/9/98/Discord_logo.svg/320px-Discord_logo.svg.png",
    "دسكورد": "https://upload.wikimedia.org/wikipedia/en/thumb/9/98/Discord_logo.svg/320px-Discord_logo.svg.png",
    "spotify": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/320px-Spotify_logo_without_text.svg.png",
    "سبوتيفاي": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/19/Spotify_logo_without_text.svg/320px-Spotify_logo_without_text.svg.png",
    "youtube": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/320px-YouTube_full-color_icon_%282017%29.svg.png",
    "يوتيوب": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/320px-YouTube_full-color_icon_%282017%29.svg.png",
    "snapchat": "https://upload.wikimedia.org/wikipedia/en/thumb/c/c4/Snapchat_logo.svg/320px-Snapchat_logo.svg.png",
    "سناب شات": "https://upload.wikimedia.org/wikipedia/en/thumb/c/c4/Snapchat_logo.svg/320px-Snapchat_logo.svg.png",
    "chatgpt": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/ChatGPT_logo.svg/320px-ChatGPT_logo.svg.png",
    "openai": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/ChatGPT_logo.svg/320px-ChatGPT_logo.svg.png",
    "mobile legends": "https://upload.wikimedia.org/wikipedia/en/thumb/0/0b/Mobile_Legends_Bang_Bang_logo.png/320px-Mobile_Legends_Bang_Bang_logo.png",
    "clash of clans": "https://upload.wikimedia.org/wikipedia/en/thumb/5/5a/Clash_of_clans_logo.png/320px-Clash_of_clans_logo.png",
    "clash royale": "https://upload.wikimedia.org/wikipedia/en/thumb/3/30/Clash_Royale_logo.png/320px-Clash_Royale_logo.png",
    "كلاش": "https://upload.wikimedia.org/wikipedia/en/thumb/3/30/Clash_Royale_logo.png/320px-Clash_Royale_logo.png",
    "bigo": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Bigo_Live_Logo.png/320px-Bigo_Live_Logo.png",
    "بيجو": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Bigo_Live_Logo.png/320px-Bigo_Live_Logo.png",
    "likee": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Likee_logo.svg/320px-Likee_logo.svg.png",
    "لايكي": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Likee_logo.svg/320px-Likee_logo.svg.png",
    "syriatel": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Syriatel_logo.svg/320px-Syriatel_logo.svg.png",
    "سيريتل": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Syriatel_logo.svg/320px-Syriatel_logo.svg.png",
    "mtn": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/MTN_Logo.svg/320px-MTN_Logo.svg.png",
    "asiacell": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/34/Asiacell_Logo.png/320px-Asiacell_Logo.png",
    "اسياسيل": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/34/Asiacell_Logo.png/320px-Asiacell_Logo.png",
    "zain": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Zain_logo.svg/320px-Zain_logo.svg.png",
    "زين": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Zain_logo.svg/320px-Zain_logo.svg.png",
    "ea fc": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/EA_Sports_FC_logo.svg/320px-EA_Sports_FC_logo.svg.png",
    "fifa": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/EA_Sports_FC_logo.svg/320px-EA_Sports_FC_logo.svg.png",
    "valorant": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fc/Valorant_logo_-_pink_color_version.svg/320px-Valorant_logo_-_pink_color_version.svg.png",
    "league of legends": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d8/League_of_Legends_2019_vector.svg/320px-League_of_Legends_2019_vector.svg.png",
    "call of duty": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Call_of_Duty_Logo.svg/320px-Call_of_Duty_Logo.svg.png",
    "brawl stars": "https://upload.wikimedia.org/wikipedia/en/thumb/4/4b/Brawl_Stars_logo.png/320px-Brawl_Stars_logo.png",
    "genshin": "https://upload.wikimedia.org/wikipedia/en/thumb/5/5d/Genshin_Impact_logo.svg/320px-Genshin_Impact_logo.svg.png",
    "nordvpn": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/NordVPN_Logo_2020.svg/320px-NordVPN_Logo_2020.svg.png",
    "expressvpn": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/ExpressVPN_logo.svg/320px-ExpressVPN_logo.svg.png",
    "kaspersky": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Kaspersky_Lab_logo.svg/320px-Kaspersky_Lab_logo.svg.png",
    "adguard": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d8/AdGuard_Logo.svg/320px-AdGuard_Logo.svg.png",
    "yalla": "https://play-lh.googleusercontent.com/s0P_uI025Jd2fP6Jb17g7gI2GjHj3d9Z4l4_vB8vC9x8w_z8=s180-rw",
    "yoyo": "https://play-lh.googleusercontent.com/uR1_f8g2_zG7z8L6pM9r=s180-rw",
    "soulchill": "https://play-lh.googleusercontent.com/pZ_9f_8kL=s180-rw",
    "chamet": "https://play-lh.googleusercontent.com/chm_98k2=s180-rw",
    "poppo": "https://play-lh.googleusercontent.com/pop_871=s180-rw",
    "canva": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Canva_icon_2021.svg/320px-Canva_icon_2021.svg.png",
    "كانفا": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Canva_icon_2021.svg/320px-Canva_icon_2021.svg.png",
    "vpn": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/NordVPN_Logo_2020.svg/320px-NordVPN_Logo_2020.svg.png",
    "browsec": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/NordVPN_Logo_2020.svg/320px-NordVPN_Logo_2020.svg.png",
    "ayome": "https://play-lh.googleusercontent.com/s0P_uI025Jd2fP6Jb17g7gI2GjHj3d9Z4l4_vB8vC9x8w_z8=s180-rw",
    "ايومي": "https://play-lh.googleusercontent.com/s0P_uI025Jd2fP6Jb17g7gI2GjHj3d9Z4l4_vB8vC9x8w_z8=s180-rw",
    "beela": "https://play-lh.googleusercontent.com/uR1_f8g2_zG7z8L6pM9r=s180-rw",
    "بيلا": "https://play-lh.googleusercontent.com/uR1_f8g2_zG7z8L6pM9r=s180-rw",
    "binmo": "https://play-lh.googleusercontent.com/pZ_9f_8kL=s180-rw",
    "بينمو": "https://play-lh.googleusercontent.com/pZ_9f_8kL=s180-rw",
    "chirp": "https://play-lh.googleusercontent.com/chm_98k2=s180-rw",
    "شيري": "https://play-lh.googleusercontent.com/chm_98k2=s180-rw",
    "cocco": "https://play-lh.googleusercontent.com/pop_871=s180-rw",
    "كوكو": "https://play-lh.googleusercontent.com/pop_871=s180-rw",
    "best live": "https://play-lh.googleusercontent.com/s0P_uI025Jd2fP6Jb17g7gI2GjHj3d9Z4l4_vB8vC9x8w_z8=s180-rw",
    "carrot": "https://play-lh.googleusercontent.com/uR1_f8g2_zG7z8L6pM9r=s180-rw",
    "جزر": "https://play-lh.googleusercontent.com/uR1_f8g2_zG7z8L6pM9r=s180-rw",
    "crashlive": "https://play-lh.googleusercontent.com/pZ_9f_8kL=s180-rw",
    "كراش": "https://play-lh.googleusercontent.com/pZ_9f_8kL=s180-rw",
}


@register.simple_tag
def product_display_image(product):
    """
    Returns the URL of the product image if uploaded, or falls back to an official
    high-resolution brand logo based on product name matching.
    """
    if not product:
        return ""

    # 1. Direct product.image
    img = getattr(product, "image", None)
    if img:
        try:
            if hasattr(img, "url") and img.url:
                return img.url
        except Exception:
            pass

    # 2. Thumbnail
    thumb = getattr(product, "thumbnail", None)
    if thumb:
        try:
            if hasattr(thumb, "url") and thumb.url:
                return thumb.url
        except Exception:
            pass

    # 3. Cover image
    cover = getattr(product, "cover_image", None)
    if cover:
        try:
            if hasattr(cover, "url") and cover.url:
                return cover.url
        except Exception:
            pass

    # 4. First gallery image
    try:
        gallery_mgr = getattr(product, "gallery", None)
        if gallery_mgr:
            first_gal = gallery_mgr.first()
            if first_gal and getattr(first_gal, "url", None):
                return first_gal.url
    except Exception:
        pass

    # 5. Category image fallback
    cat = getattr(product, "category", None)
    if cat and getattr(cat, "image", None):
        try:
            if hasattr(cat.image, "url") and cat.image.url:
                return cat.image.url
        except Exception:
            pass

    # 6. Brand logo matching
    p_name = getattr(product, "name", "").lower()
    for brand, url in BRAND_LOGOS_MAP.items():
        if brand in p_name:
            return url

    return ""


