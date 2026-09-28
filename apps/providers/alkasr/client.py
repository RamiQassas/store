"""
Unified Client Adapter for apps.providers.alkasr.
Re-exports centralized AlkasrAPIClient from services.provider.alkasr.client
to ensure a single source of truth and eliminate duplicate client logic.
"""

from services.provider.alkasr.client import AlkasrAPIClient, AlkasrClient

__all__ = ["AlkasrAPIClient", "AlkasrClient"]
