"""
Comprehensive Pricing Engine for Alkasr Provider Integration.
Supports percentage, fixed, percentage+fixed, manual overrides, currency exchange, and rounding.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any


class PricingEngine:
    """
    Calculates final dynamic pricing for products based on cost price, customer tier, rules, and exchange rates.
    """

    @staticmethod
    def round_price(price: Decimal, nearest: int = 1) -> Decimal:
        """Rounds price to nearest integer or step if requested."""
        if nearest <= 0:
            return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal(round(float(price) / nearest) * nearest).quantize(Decimal("0.01"))

    @classmethod
    def calculate_final_price(
        cls,
        base_cost: Decimal,
        margin_type: str = "percentage",
        margin_value: Decimal = Decimal("5.00"),
        fixed_addition: Decimal = Decimal("0.00"),
        manual_price: Optional[Decimal] = None,
        round_to_nearest: bool = False,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        exchange_rate: Decimal = Decimal("1.00"),
        customer_tier: Optional[str] = None
    ) -> Dict[str, Decimal]:
        """
        Calculates:
        - Base Price in USD
        - Margin Amount
        - Final Price in Base Currency (USD)
        - Final Price in Customer Currency
        - Estimated Profit in USD
        """
        cost = Decimal(str(base_cost or "0.00"))
        rate = Decimal(str(exchange_rate or "1.00"))

        if margin_type == "manual" and manual_price is not None and manual_price > Decimal("0"):
            base_final = Decimal(str(manual_price))
        else:
            m_val = Decimal(str(margin_value or "0.00"))
            f_add = Decimal(str(fixed_addition or "0.00"))

            if margin_type == "fixed":
                base_final = cost + m_val
            elif margin_type == "percentage":
                base_final = cost + (cost * (m_val / Decimal("100.0")))
            elif margin_type == "percentage_fixed":
                base_final = cost + (cost * (m_val / Decimal("100.0"))) + f_add
            else:
                base_final = cost + (cost * (m_val / Decimal("100.0")))

        if min_price is not None and base_final < min_price:
            base_final = Decimal(str(min_price))
        if max_price is not None and base_final > max_price:
            base_final = Decimal(str(max_price))

        if round_to_nearest:
            base_final = cls.round_price(base_final)

        customer_final = (base_final * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        profit = (base_final - cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "base_cost": cost.quantize(Decimal("0.01")),
            "base_final_price": base_final.quantize(Decimal("0.01")),
            "customer_final_price": customer_final,
            "exchange_rate": rate,
            "profit": profit,
        }
