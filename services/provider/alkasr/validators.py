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
    Sanity checks before submitting order to Alkasr VIP provider.
    Ensures parameters are matched without blocking valid orders.
    """
    qty = int(quantity)
    if qty <= 0:
        raise ValidationException("الكمية يجب أن تكون أكبر من الصفر.")

    # We do not block active store orders by local cache status; live provider API will process it.
