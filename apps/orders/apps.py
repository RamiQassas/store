import os
import sys
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"

    def ready(self):
        # Only start in runtime server process, avoid migrations/collectstatic
        if "runserver" in sys.argv or "daphne" in sys.argv or "gunicorn" in sys.argv or "uvicorn" in sys.argv or os.environ.get("RUN_MAIN") == "true" or not sys.argv:
            try:
                import time
                import logging
                import threading
                from django.db import connection

                logger = logging.getLogger("order_sync_daemon")

                def _run_order_sync():
                    while True:
                        try:
                            time.sleep(12)
                            connection.close()
                            from apps.orders.models import Order
                            from services.provider.manager import ProviderManager
                            from apps.orders.provider_status import apply_provider_status
                            from apps.providers.models import ProviderProfile

                            default_profile = ProviderProfile.objects.filter(is_active=True).first()

                            pending_orders = Order.all_objects.filter(
                                status__in=[Order.Status.PROCESSING, Order.Status.PENDING]
                            ).exclude(api_order_uuid=None, api_order_id=None)[:25]

                            for order in pending_orders:
                                try:
                                    current_api_status = str((order.fulfillment_data or {}).get("api_status") or "").lower()
                                    if current_api_status in ("error", "failed", "reject", "rejected", "cancel", "cancelled", "refused", "declined"):
                                        apply_provider_status(order, current_api_status, raw_response=order.fulfillment_data, actor=None, note_prefix="مزامنة خلفية")
                                        continue

                                    po = order.provider_orders.select_related("profile").first()
                                    profile = po.profile if (po and po.profile) else default_profile
                                    if profile:
                                        if order.api_order_id:
                                            identifiers = [str(order.api_order_id)]
                                            is_uuid = False
                                        elif order.api_order_uuid:
                                            identifiers = [str(order.api_order_uuid)]
                                            is_uuid = True
                                        else:
                                            continue

                                        data_list = ProviderManager.check_orders(
                                            profile,
                                            identifiers,
                                            is_uuid=is_uuid
                                        )
                                        if data_list and len(data_list) > 0:
                                            order_data = data_list[0]
                                            api_status = order_data.get("status")
                                            apply_provider_status(order, api_status, raw_response=order_data, actor=None, note_prefix="مزامنة خلفية")
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        finally:
                            try:
                                connection.close()
                            except Exception:
                                pass

                t = threading.Thread(target=_run_order_sync, daemon=True, name="OrderSyncDaemon")
                t.start()
                logger.info("⚡ [ORDER-SYNC] Background order status sync daemon started.")
            except Exception:
                pass
