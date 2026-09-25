import logging
from typing import Optional, Tuple, List, Dict, Any
from django.db.models import Q

logger = logging.getLogger("order_sync")


def resolve_order_provider_profile(order) -> Optional[Any]:
    """
    Deterministically resolves the correct ProviderProfile for a given Order.
    Checks:
    1. Associated ProviderOrder records.
    2. Explicit provider string in order metadata or fulfillment_data.
    3. Variant configuration via resolve_variant_provider_and_product.
    4. Product-level api_provider field.
    5. Tenant-specific active ProviderProfile.
    6. Main platform active ProviderProfile fallback.
    """
    from apps.providers.models import ProviderProfile
    from apps.orders.services import resolve_variant_provider_and_product
    from apps.common.tenant_utils import bypass_tenant_filter

    with bypass_tenant_filter():
        # 1. Direct ProviderOrder association
        po = order.provider_orders.select_related("profile").first()
        if po and po.profile and po.profile.is_active:
            return po.profile

        # 2. Metadata / fulfillment_data provider key
        provider_name = ""
        if isinstance(order.metadata, dict):
            provider_name = order.metadata.get("api_provider") or ""
        if not provider_name and isinstance(order.fulfillment_data, dict):
            provider_name = order.fulfillment_data.get("api_provider") or ""

        if provider_name:
            clean_name = str(provider_name).strip()
            # Match by provider_name or provider type
            profile = ProviderProfile.all_objects.filter(
                is_active=True
            ).filter(
                Q(provider_name__iexact=clean_name) |
                Q(base_url__icontains=clean_name.lower())
            ).first()
            if profile:
                return profile

        # 3. Resolve from ordered product variant
        first_item = order.items.select_related("variant__product").first()
        if first_item and first_item.variant:
            try:
                _, resolved_profile = resolve_variant_provider_and_product(first_item.variant)
                if resolved_profile and resolved_profile.is_active:
                    return resolved_profile
            except Exception:
                pass

            # 4. Product-level api_provider
            prod = getattr(first_item.variant, "product", None)
            if prod and getattr(prod, "api_provider", None):
                p_name = str(prod.api_provider).strip()
                profile = ProviderProfile.all_objects.filter(
                    is_active=True
                ).filter(
                    Q(provider_name__iexact=p_name) |
                    Q(base_url__icontains=p_name.lower())
                ).first()
                if profile:
                    return profile

        # 5. Store specific profile if applicable
        if order.store:
            profile = ProviderProfile.all_objects.filter(store=order.store, is_active=True).first()
            if profile:
                return profile

        # 6. Global platform fallback
        return ProviderProfile.all_objects.filter(is_active=True).first()


def sync_single_order_status(order, actor=None, note_prefix="تحديث تلقائي") -> Tuple[bool, Any, str]:
    """
    Checks provider status for a single order and updates order status atomically.
    Returns:
        (updated: bool, order: Order, current_status: str)
    """
    from apps.orders.models import Order
    from apps.orders.provider_status import apply_provider_status
    from services.provider.manager import ProviderManager

    if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.REFUNDED):
        return False, order, order.status

    fulfillment = dict(order.fulfillment_data or {})
    old_status = order.status

    # Fast-path 1: If fulfillment_data already recorded an accept/reject status
    status_completed_aliases = {
        "accept", "accepted", "completed", "complete", "success", "successful",
        "done", "approved", "1", 1, "تم الشحن", "مكتمل", "تم التنفيذ"
    }
    status_cancelled_aliases = {
        "error", "failed", "reject", "rejected", "cancel", "cancelled", "refused", "declined", "2", 2, "3", 3, "-1", -1
    }

    current_api_status = str(fulfillment.get("api_status") or "").lower()
    if current_api_status in status_cancelled_aliases or current_api_status in status_completed_aliases:
        order = apply_provider_status(
            order,
            current_api_status,
            raw_response=fulfillment.get("api_last_response") or fulfillment,
            actor=actor,
            note_prefix=note_prefix
        )
        return (order.status != old_status), order, order.status

    # Fast-path 2: Check attached ProviderOrder records
    po = order.provider_orders.select_related("profile").first()
    if po:
        po_status = str(po.status or "").lower()
        if po_status in status_completed_aliases or po_status in status_cancelled_aliases:
            latest_status_rec = po.status_history.order_by("-created_at").first()
            raw_resp = latest_status_rec.raw_response if latest_status_rec and latest_status_rec.raw_response else {"po_status": po_status}
            order = apply_provider_status(
                order,
                po_status,
                raw_response=raw_resp,
                actor=actor,
                note_prefix=note_prefix
            )
            return (order.status != old_status), order, order.status

    profile = resolve_order_provider_profile(order)
    if not profile:
        return False, order, order.status

    # Extract all possible remote identifiers from Order, PO, fulfillment, metadata
    meta = order.metadata if isinstance(order.metadata, dict) else {}
    remote_id = (
        order.api_order_id or
        (str(po.remote_order_id) if po and po.remote_order_id else None) or
        fulfillment.get("api_order_id") or
        fulfillment.get("order_id") or
        fulfillment.get("remote_order_id") or
        meta.get("api_order_id") or
        meta.get("remote_order_id")
    )
    remote_uuid = (
        order.api_order_uuid or
        (str(po.uuid) if po and po.uuid else None) or
        fulfillment.get("api_order_uuid") or
        fulfillment.get("uuid") or
        meta.get("order_uuid") or
        meta.get("api_order_uuid")
    )

    update_fields = []
    if remote_id and not order.api_order_id:
        order.api_order_id = str(remote_id)
        update_fields.append("api_order_id")
    if remote_uuid and not order.api_order_uuid:
        order.api_order_uuid = str(remote_uuid)
        update_fields.append("api_order_uuid")
    if update_fields:
        order.save(update_fields=update_fields)

    data_list: List[Dict[str, Any]] = []

    try:
        # Check by remote api_order_id first
        if remote_id:
            data_list = ProviderManager.check_orders(
                profile,
                [str(remote_id)],
                is_uuid=False
            )

        # Fallback to api_order_uuid if no status received
        if not data_list and remote_uuid:
            data_list = ProviderManager.check_orders(
                profile,
                [str(remote_uuid)],
                is_uuid=True
            )
    except Exception as exc:
        logger.warning(
            "Provider status check failed for order %s (profile=%s): %s",
            order.number, getattr(profile, "provider_name", "unknown"), exc
        )
        return False, order, order.status

    if not data_list:
        return False, order, order.status

    order_data = data_list[0]
    api_status = order_data.get("status") or order_data.get("raw_status")

    if not api_status:
        return False, order, order.status

    order = apply_provider_status(
        order,
        api_status,
        raw_response=order_data,
        actor=actor,
        note_prefix=note_prefix
    )

    is_changed = (order.status != old_status)
    return is_changed, order, order.status


def sync_pending_orders_batch(orders_qs=None, limit=100) -> Dict[str, Any]:
    """
    Synchronizes status of pending/processing orders in batch.
    Safe against exceptions, returns detailed summary of checked, updated, completed, and cancelled counts.
    """
    from apps.orders.models import Order
    from apps.common.tenant_utils import bypass_tenant_filter

    if orders_qs is None:
        with bypass_tenant_filter():
            orders_qs = (
                Order.all_objects.filter(
                    status__in=[Order.Status.PROCESSING, Order.Status.PENDING]
                )
                .select_related("customer", "store")
                .prefetch_related("items__variant__product", "provider_orders__profile")
                .order_by("created_at")[:limit]
            )

    checked = 0
    updated = 0
    completed_count = 0
    cancelled_count = 0
    errors = 0
    updated_orders = []

    for order in orders_qs:
        checked += 1
        try:
            changed, updated_order, status = sync_single_order_status(order, actor=None, note_prefix="تحديث تلقائي للمزود")
            if changed:
                updated += 1
                if status == Order.Status.COMPLETED:
                    completed_count += 1
                elif status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
                    cancelled_count += 1

                updated_orders.append({
                    "id": str(updated_order.id),
                    "number": updated_order.number,
                    "status": status,
                    "status_display": updated_order.get_status_display()
                })
        except Exception as exc:
            errors += 1
            logger.error("Error syncing order %s: %s", getattr(order, "id", None), exc)

    return {
        "checked": checked,
        "updated": updated,
        "completed": completed_count,
        "cancelled": cancelled_count,
        "errors": errors,
        "updated_orders": updated_orders
    }
