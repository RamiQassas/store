import logging
from django.http import HttpResponsePermanentRedirect
from django.core.cache import cache
from django.utils import timezone
from django.db import models

logger = logging.getLogger(__name__)


class DomainRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()
        # The primary domain we want to enforce
        primary_domain = 'raqamiyatapp.com'
        
        # If the request comes from the old onrender domain, redirect to the new one
        if 'raqamiyat.onrender.com' in host:
            new_url = f"https://{primary_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)
            
        # If the request comes from www.raqamiyatapp.com, redirect to canonical apex domain
        clean_host = host.split(':')[0]
        if clean_host == 'www.raqamiyatapp.com':
            new_url = f"https://{primary_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)

        return self.get_response(request)


def record_server_error_and_notify(request, exception=None, status_code=500):
    """
    Creates an in-app high-priority notification for admins and records a SystemAuditLog
    whenever an unhandled 500 error occurs. Uses a throttle cache to avoid flooding identical errors.
    """
    try:
        path = getattr(request, "path", "unknown")
        method = getattr(request, "method", "GET")
        user = getattr(request, "user", None)
        user_str = f"{user.email} (ID: {user.id})" if user and user.is_authenticated else "زائر غير مسجل (Anonymous)"

        meta = getattr(request, "META", {})
        ip = meta.get("HTTP_X_FORWARDED_FOR")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = meta.get("REMOTE_ADDR")

        exc_msg = str(exception) if exception else "خطأ غير متوقع في الخادم (500 Internal Server Error)"

        # Throttle: max 1 notification per unique error path every 60 seconds (safe hashed key)
        import hashlib
        raw_key_seed = f"{path}_{method}_{exc_msg[:50]}".encode("utf-8")
        throttle_key = f"err_notify_{hashlib.md5(raw_key_seed).hexdigest()}"
        if cache.get(throttle_key):
            return
        cache.set(throttle_key, True, 60)

        # 1. Permanent Audit Log in Control Panel
        try:
            from apps.common.models import SystemAuditLog
            SystemAuditLog.objects.create(
                actor=user if user and user.is_authenticated else None,
                action_type="server_error_500",
                description=f"خطأ 500 على [{method} {path}] للمستخدم: {user_str}. الخطأ: {exc_msg[:250]}",
                ip_address=ip if (ip and len(ip) <= 45) else None,
                reason=exc_msg[:500]
            )
        except Exception as e:
            logger.warning("Failed to create SystemAuditLog for 500 error: %s", e)

        # 2. In-App High-Priority Notification for Admins in Control Panel
        try:
            from django.contrib.auth import get_user_model
            from apps.notifications.models import Notification
            User = get_user_model()
            admins = User.objects.filter(
                models.Q(is_superuser=True) | models.Q(is_staff=True),
                is_active=True
            )[:10]

            full_url = request.get_full_path() if hasattr(request, "get_full_path") else path
            title = f"⚠️ تنبيه: خطأ في الخادم (500) على المسار {path[:45]}"
            body = (
                f"واجه العميل/المستخدم: {user_str}\n"
                f"المسار: {method} {full_url}\n"
                f"عنوان IP: {ip or 'غير معروف'}\n"
                f"الخطأ: {exc_msg[:250]}\n"
                f"الوقت: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            for adm in admins:
                Notification.objects.create(
                    user=adm,
                    channel=Notification.Channel.IN_APP,
                    priority=Notification.Priority.HIGH,
                    title=title,
                    body=body,
                    action_url=path if path.startswith("/") else None,
                    metadata={
                        "path": path,
                        "method": method,
                        "user": user_str,
                        "ip": ip,
                        "error": exc_msg[:300]
                    }
                )
        except Exception as e:
            logger.warning("Failed to create Notification for 500 error: %s", e)

    except Exception as e:
        logger.error("Error in record_server_error_and_notify: %s", e)


class ServerErrorNotificationMiddleware:
    """
    Middleware that intercepts exceptions and notifies administrators in real-time.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 500:
            record_server_error_and_notify(request, status_code=response.status_code)
        return response

    def process_exception(self, request, exception):
        record_server_error_and_notify(request, exception=exception, status_code=500)
        return None
