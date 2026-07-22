from decimal import Decimal
from django.db import transaction
from django.db.models import F
from apps.providers.models import ProviderProduct, ProviderPrice, ProviderPriceHistory

class PricingService:
    @staticmethod
    @transaction.atomic
    def bulk_update_margin(products_qs, margin_type, margin_value, user=None):
        """
        Updates the margin for a queryset of ProviderProduct.
        Supports:
        margin_type: 'fixed' or 'percentage'
        margin_value: Decimal
        """
        updated_count = 0
        for product in products_qs:
            pricing = product.pricing
            
            old_cost = product.cost_price
            old_final = pricing.final_price
            
            pricing.margin_type = margin_type
            pricing.margin_value = margin_value
            pricing.save()
            
            new_final = pricing.final_price
            
            if old_final != new_final:
                ProviderPriceHistory.objects.create(
                    product=product,
                    changed_by=user,
                    old_cost=old_cost,
                    new_cost=old_cost,
                    old_final_price=old_final,
                    new_final_price=new_final,
                    reason="Bulk margin update"
                )
            
            updated_count += 1
            
        return updated_count
