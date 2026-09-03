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
    qty_min = meta.get("qty_min", 1)
    qty_list = meta.get("qty_list", [])
    is_per_mille = meta.get("is_per_mille", False)
    
    min_multiplier = Decimal("1")
    if qty_type == "range":
        try:
            min_val = Decimal(str(qty_min)) if qty_min else Decimal("1")
            if min_val > 1:
                min_multiplier = min_val
        except Exception:
            pass
    elif (qty_type == "list" or qty_list) and is_per_mille:
        try:
            valid_list = [Decimal(str(x)) for x in qty_list if Decimal(str(x)) > 0]
            if valid_list:
                min_multiplier = min(valid_list)
        except Exception:
            pass
    elif is_per_mille and qty_min:
        try:
            min_val = Decimal(str(qty_min))
            if min_val > 1:
                min_multiplier = min_val
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
        qty_min = meta.get("qty_min", 1)
        qty_list = meta.get("qty_list", [])
        is_per_mille = meta.get("is_per_mille", False)
        
        min_multiplier = Decimal("1")
        if qty_type == "range":
            try:
                min_val = Decimal(str(qty_min)) if qty_min else Decimal("1")
                if min_val > 1:
                    min_multiplier = min_val
            except Exception:
                pass
        elif (qty_type == "list" or qty_list) and is_per_mille:
            try:
                valid_list = [Decimal(str(x)) for x in qty_list if Decimal(str(x)) > 0]
                if valid_list:
                    min_multiplier = min(valid_list)
            except Exception:
                pass
        elif is_per_mille and qty_min:
            try:
                min_val = Decimal(str(qty_min))
                if min_val > 1:
                    min_multiplier = min_val
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
        if "," in val:
            return [x.strip() for x in val.split(",") if x.strip()]
    if val is not None and val != "":
        return [val]
    return []


