"""
Alkasr Order Reconciliation Engine.
Periodically audits and synchronizes pending/processing provider orders with Alkasr VIP API.
Ensures no orders remain stuck in limbo and prevents premature refunds on transient network errors.
"""

import logging
from datetime import timedelta
from typing import Dict, Any, List

from django.utils import timezone
from django.db import transaction

from .client import AlkasrAPIClient
from .constants import PROVIDER_STATUS_MAP

logger = logging.getLogger("provider.alkasr.reconciliation")


class AlkasrReconciliationService:
    """Service to reconcile pending orders with Alkasr VIP API."""

    def __init__(self, profile, client: AlkasrAPIClient = None):
        self.profile = profile
        self.client = client or AlkasrAPIClient(
            api_token=getattr(profile, "api_token", None),
            base_url=getattr(profile, "base_url", None),
            profile=profile
        )

    def reconcile_pending_orders(self, days: int = 7, batch_size: int = 50) -> Dict[str, Any]:
        """
        Reconciles pending and processing orders from the last `days` days.
        Queries Alkasr /check endpoint in batches.
        """
        from apps.providers.models import ProviderOrder, ProviderOrderStatus
        from apps.orders.provider_status import apply_provider_status

        cutoff_date = timezone.now() - timedelta(days=days)
        pending_qs = ProviderOrder.objects.filter(
            profile=self.profile,
            status__in=["pending", "processing", "waiting"],
            created_at__gte=cutoff_date
        ).select_related("local_order").order_by("created_at")

        total_orders = pending_qs.count()
        if total_orders == 0:
            return {
                "checked": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "errors": 0,
                "details": []
            }

        stats = {
            "checked": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "errors": 0,
            "details": []
        }

        # Separate orders into those with remote_order_id and those with only UUID
        orders_with_id = []
        orders_with_uuid_only = []

        for po in pending_qs:
            if po.remote_order_id:
                orders_with_id.append(po)
            elif po.uuid:
                orders_with_uuid_only.append(po)

        # Batch 1: Check by remote_order_id
        for i in range(0, len(orders_with_id), batch_size):
            chunk = orders_with_id[i:i + batch_size]
            id_list = [str(o.remote_order_id) for o in chunk]
            try:
                res = self.client.check_orders(order_ids=id_list)
                self._process_check_results(res, chunk, stats, is_uuid=False)
            except Exception as exc:
                logger.error("Failed to check orders chunk %s: %s", id_list, exc)
                stats["errors"] += len(chunk)

        # Batch 2: Check by UUID
        for i in range(0, len(orders_with_uuid_only), batch_size):
            chunk = orders_with_uuid_only[i:i + batch_size]
            uuid_list = [str(o.uuid) for o in chunk]
            try:
                res = self.client.check_orders(order_uuids=uuid_list)
                self._process_check_results(res, chunk, stats, is_uuid=True)
            except Exception as exc:
                logger.error("Failed to check UUID chunk %s: %s", uuid_list, exc)
                stats["errors"] += len(chunk)

        return stats

    def _process_check_results(self, response_data: Any, orders_chunk: List[Any], stats: Dict[str, Any], is_uuid: bool = False):
        """Processes check response items and updates ProviderOrder and store Order."""
        from apps.providers.models import ProviderOrderStatus
        from apps.orders.provider_status import apply_provider_status

        items = []
        if isinstance(response_data, list):
            items = response_data
        elif isinstance(response_data, dict):
            raw_data = response_data.get("data")
            if isinstance(raw_data, list):
                items = raw_data
            elif isinstance(raw_data, dict):
                items = [raw_data]
            elif "orders" in response_data and isinstance(response_data["orders"], list):
                items = response_data["orders"]
            else:
                items = [response_data]

        # Index chunk by id and by uuid
        chunk_by_id = {str(o.remote_order_id): o for o in orders_chunk if o.remote_order_id}
        chunk_by_uuid = {str(o.uuid): o for o in orders_chunk if o.uuid}

        for item in items:
            if not isinstance(item, dict):
                continue

            item_id = str(item.get("order_id") or item.get("id") or "").strip()
            item_uuid = str(item.get("order_uuid") or item.get("uuid") or "").strip()

            po = chunk_by_id.get(item_id) or chunk_by_uuid.get(item_uuid)
            if not po:
                continue

            stats["checked"] += 1
            raw_status = str(item.get("status") or "").strip().lower()
            mapped_status = PROVIDER_STATUS_MAP.get(raw_status, "pending")

            with transaction.atomic():
                po.status = mapped_status
                if item_id and not po.remote_order_id:
                    po.remote_order_id = item_id
                po.save(update_fields=["status", "remote_order_id", "updated_at"])

                ProviderOrderStatus.objects.create(
                    provider_order=po,
                    status=mapped_status,
                    raw_response=item
                )

                # Update linked store Order if available
                if po.local_order:
                    apply_provider_status(
                        order=po.local_order,
                        provider_status=mapped_status,
                        raw_response=item,
                        note_prefix="مطابقة دورية للمزود (Reconciliation)"
                    )

            if mapped_status == "completed":
                stats["completed"] += 1
            elif mapped_status in ("failed", "rejected", "cancelled"):
                stats["failed"] += 1
            else:
                stats["pending"] += 1

            stats["details"].append({
                "po_id": po.id,
                "remote_id": po.remote_order_id,
                "uuid": po.uuid,
                "status": mapped_status,
                "raw_status": raw_status
            })
