"""
Pre-order validators for Alkasr VIP Provider.
Performs strict validation before submitting orders to provider API.
"""

from decimal import Decimal
from typing import Dict, Any
from .exceptions import ValidationException


def validate_order_preconditions(
    provider_product,
    quantity: int,
    parameters_sent: Dict[str, Any],
    provider_balance: Decimal = None,
    order_cost: Decimal = None
) -> None:
    """
    Validates balance, quantity limits, product availability, and required player parameters.
    Raises ValidationException if any condition fails.
    """
    # 1. Product availability check
    if not getattr(provider_product, "is_active", True):
        raise ValidationException("المنتج غير فعال لدى المزود حالياً.")

    if not getattr(provider_product, "local_is_active", True):
        raise ValidationException("المنتج غير فعال في المتجر حالياً.")

    # 2. Quantity bounds check
    qty = int(quantity)
    if qty <= 0:
        raise ValidationException("الكمية يجب أن تكون أكبر من الصفر.")

    qty_min = getattr(provider_product, "qty_min", None)
    if qty_min is not None and qty < qty_min:
        raise ValidationException(f"الكمية المطلوبة ({qty}) أقل من الحد الأدنى المسموح ({qty_min}).")

    qty_max = getattr(provider_product, "qty_max", None)
    if qty_max is not None and qty > qty_max:
        raise ValidationException(f"الكمية المطلوبة ({qty}) أكبر من الحد الأقصى المسموح ({qty_max}).")

    # 3. Fixed quantities check
    qty_list = getattr(provider_product, "qty_list", None)
    if qty_list and isinstance(qty_list, list) and len(qty_list) > 0:
        valid_quantities = [int(q) for q in qty_list if str(q).isdigit()]
        if valid_quantities and qty not in valid_quantities:
            raise ValidationException(f"الكمية المطلوبة ({qty}) غير موجودة ضمن قائمة الكميات المتاحة: {valid_quantities}")

    # 4. Required parameters check
    parameters = provider_product.parameters.filter(required=True) if hasattr(provider_product, "parameters") else []
    for param in parameters:
        val = parameters_sent.get(param.name) or parameters_sent.get(param.label)
        if not val and (param.name == "playerId" or "id" in (param.name or "").lower() or "ايدي" in (param.label or "")):
            for k, v in parameters_sent.items():
                if any(alias in k.lower() for alias in ["player", "user", "id", "ايدي", "آيدي"]):
                    val = v
                    break
        if not val or not str(val).strip():
            raise ValidationException(f"الحقل المطلوب '{param.label or param.name}' غير متوفر أو فارغ.")

    # 5. Balance check
    if provider_balance is not None and order_cost is not None:
        if Decimal(str(provider_balance)) < Decimal(str(order_cost)):
            raise ValidationException(
                f"رصيد المزود الحالي ({provider_balance}) غير كافٍ لإتمام طلب بتكلفة ({order_cost})."
            )
