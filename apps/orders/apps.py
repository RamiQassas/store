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
                    from apps.orders.sync_service import sync_pending_orders_batch
                    from django.core.cache import cache
                    while True:
                        try:
                            time.sleep(30)
                            # Distributed lock: only one worker processes order status sync at a time
                            lock_acquired = cache.add("order_sync_daemon_lock", "active", timeout=60)
                            if not lock_acquired:
                                continue
                            connection.close()
                            sync_pending_orders_batch(limit=15)
                        except Exception as exc:
                            logger.error("OrderSyncDaemon error: %s", exc)
                        finally:
                            try:
                                cache.delete("order_sync_daemon_lock")
                                connection.close()
                            except Exception:
                                pass

                t = threading.Thread(target=_run_order_sync, daemon=True, name="OrderSyncDaemon")
                t.start()
                logger.info("⚡ [ORDER-SYNC] Background order status sync daemon started (interval=8s).")
            except Exception:
                pass
