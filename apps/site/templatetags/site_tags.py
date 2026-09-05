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



