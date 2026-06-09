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
def currency_format(context, amount, source_currency=None):
    """
    Formats a price according to the current preferred currency in context.
    If source_currency is provided, it converts from it to preferred.
    Otherwise, assumes amount is in SYSTEM_CURRENCY.
    """
    target_currency = context.get('CURRENCY')
    system_currency = context.get('SYSTEM_CURRENCY')
    
    if not target_currency:
        return f"{amount} SYP"
        
    try:
        source = source_currency or system_currency
        
        if source and target_currency and source.code == target_currency.code:
             formatted = f"{Decimal(str(amount)):,.{target_currency.decimal_places}f}"
             return f"{formatted} {target_currency.symbol}"

        base_amount = amount
        if source and source.code != "USD":
            base_amount = source.to_base(amount)
        
        converted = target_currency.from_base(base_amount)
        formatted = f"{converted:,.{target_currency.decimal_places}f}"
        return f"{formatted} {target_currency.symbol}"
    except Exception:
        return f"{amount} {target_currency.symbol if target_currency else 'SYP'}"

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
        
    # Handle JSON string if dictionary is passed as string
    if isinstance(dictionary, str):
        import json
        try:
            dictionary = json.loads(dictionary)
        except:
            return None
            
    if not isinstance(dictionary, dict):
        return None
        
    # Standard string lookup (common for JSONField)
    res = dictionary.get(str(key))
    
    # Fallback for UUID hex format if standard str(key) fails
    if res is None and hasattr(key, 'hex'):
        res = dictionary.get(key.hex)
        
    return res

@register.simple_tag
def get_deposit_config(payment_method, user):
    return payment_method.to_deposit_json(user=user)

@register.simple_tag
def get_withdrawal_config(payment_method, user):
    return payment_method.to_withdrawal_json(user=user)
