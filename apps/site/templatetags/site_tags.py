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
            
        formatted = f"{converted:,.{target_currency.decimal_places}f}"
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
    return mark_safe(payment_method.to_deposit_json(user=user))

@register.simple_tag
def get_withdrawal_config(payment_method, user):
    return mark_safe(payment_method.to_withdrawal_json(user=user))
