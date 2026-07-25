"""
Legacy Compatibility Alias.
Forwards all imports to new central services layer services.provider.alkasr.
"""

from services.provider.alkasr import (
    AlkasrClient,
    AlkasrProviderService,
    AlkasrSyncService,
    AlkasrOrderService,
    AlkasrProductService,
    AlkasrProfileService,
    PricingEngine,
    AlkasrAPIException,
)

__all__ = [
    "AlkasrClient",
    "AlkasrProviderService",
    "AlkasrSyncService",
    "AlkasrOrderService",
    "AlkasrProductService",
    "AlkasrProfileService",
    "PricingEngine",
    "AlkasrAPIException",
]
