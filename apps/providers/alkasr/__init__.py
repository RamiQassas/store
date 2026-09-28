"""
Legacy Compatibility Alias.
Forwards all imports to new central services layer services.provider.alkasr.
"""

from services.provider.alkasr import (
    AlkasrAPIClient,
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
    "AlkasrAPIClient",
    "AlkasrClient",
    "AlkasrProviderService",
    "AlkasrSyncService",
    "AlkasrOrderService",
    "AlkasrProductService",
    "AlkasrProfileService",
    "PricingEngine",
    "AlkasrAPIException",
]
