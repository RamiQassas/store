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


def is_scanner_or_exploit_probe(request, path, exc_msg):
    """Detects automated bot scanners, exploit probes, and malicious crawler requests."""
    path_lower = str(path or "").lower()
    meta = getattr(request, "META", {})
    ua = meta.get("HTTP_USER_AGENT", "").lower()
    
    # Common exploit / scanner file extensions
    SUSPICIOUS_EXTENSIONS = (
        ".php", ".asp", ".aspx", ".jsp", ".cgi", ".env", ".git", ".yaml", ".yml",
        ".bak", ".sql", ".tar", ".gz", ".rar", ".zip", ".ini", ".conf", ".cfg"
    )
    if any(path_lower.endswith(ext) or (ext + "/") in path_lower or (ext + "?") in path_lower for ext in SUSPICIOUS_EXTENSIONS):
        return True

    # Suspicious probe paths
    SUSPICIOUS_PATHS = (
        "wp-", "wordpress", "phpmyadmin", "pma", "cgi-bin", "boaform", "hnap",
        "actuator", "solr", "setup.cgi", "console", "telescope", "debug",
        ".well-known", "autodiscover", "owa", "exchange", "invoker", "jmx-console"
    )
    if any(sp in path_lower for sp in SUSPICIOUS_PATHS):
        return True

    # Exploit payloads / SQL injection / XSS / Traversal patterns in query string or path
    query_str = meta.get("QUERY_STRING", "").lower()
    combined = f"{path_lower}?{query_str}"
    EXPLOIT_PATTERNS = (
        "../", "..\\", "%2e%2e", "<script", "%3cscript", "union+select", "select+",
        "information_schema", "benchmark(", "sleep(", "waitfor+delay", "order+by+",
        "etc/passwd", "win.ini", "eval(", "base64_decode"
    )
    if any(ep in combined for ep in EXPLOIT_PATTERNS):
        return True

    # Known scanner / bot user agents
    SCANNER_AGENTS = (
        "sqlmap", "nikto", "nmap", "masscan", "zgrab", "gobuster", "dirbuster",
        "wprecon", "wpscan", "openvas", "nessus", "metasploit", "acunetix",
        "python-requests", "go-http-client", "curl/"
    )
    if any(sa in ua for sa in SCANNER_AGENTS):
        return True

    return False

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

        # Check if this is an automated bot probe or exploit scan
        if is_scanner_or_exploit_probe(request, path, exc_msg):
            # Log silently in SystemAuditLog without emailing or spamming the admin
            try:
                from apps.common.models import SystemAuditLog
                SystemAuditLog.objects.create(
                    actor=None,
                    action_type="bot_scan_blocked",
                    description=f"رصد محاولة فحص آلي/اختراق مشبوهة على [{method} {path}] من IP: {ip}",
                    ip_address=ip if (ip and len(ip) <= 45) else None,
                    reason=exc_msg[:500]
                )
            except Exception:
                pass
            return

        # Throttle: max 1 in-app notification per 5 minutes for identical path/error
        import hashlib
        raw_key_seed = f"{path}_{method}_{exc_msg[:50]}".encode("utf-8")
        throttle_key = f"err_notify_{hashlib.md5(raw_key_seed).hexdigest()}"
        if cache.get(throttle_key):
            return
        cache.set(throttle_key, True, 300)

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

        # 2. Multi-channel Notification (In-App, Push & Email) for Admins
        try:
            from django.contrib.auth import get_user_model
            from apps.notifications.models import Notification
            from apps.notifications.services import notify_user
            from apps.accounts.services import send_brevo_email
            
            User = get_user_model()
            admins = User.objects.filter(
                models.Q(is_superuser=True) | models.Q(is_staff=True),
                is_active=True
            ).distinct()

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
                try:
                    notify_user(
                        user=adm,
                        title=title,
                        body=body,
                        action_url=path if path.startswith("/") else "/control/",
                        category="system",
                        priority=Notification.Priority.URGENT,
                        metadata={
                            "path": path,
                            "method": method,
                            "user": user_str,
                            "ip": ip,
                            "error": exc_msg[:300]
                        }
                    )
                except Exception as ex_adm:
                    logger.warning("Failed to notify admin %s: %s", getattr(adm, "email", adm), ex_adm)

            # Direct Instant Email Alert to Superusers (strictly throttled: max 1 email per hour)
            email_throttle_key = "admin_500_email_hourly_throttle"
            can_send_email = not bool(cache.get(email_throttle_key))
            if can_send_email:
                cache.set(email_throttle_key, True, 3600)  # 1 hour throttle
                superusers = admins.filter(is_superuser=True)
                for su in superusers:
                    if getattr(su, "email", None):
                        try:
                            email_html = f"""
                            <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f172a; color: #f8fafc; padding: 25px; border-radius: 16px; border: 1px solid #ef4444;">
                                <h2 style="color: #ef4444; margin-top: 0; font-size: 20px;">⚠️ تنبيه رصد خطأ 500 في موقع رقميات</h2>
                                <p style="color: #94a3b8; font-size: 13px; line-height: 1.6;">تم رصد حدوث خطأ خادم داخلي (500 Server Error) عند محاولة أحد المستخدمين الوصول إلى الرابط أدناه:</p>
                                <div style="background: #1e293b; padding: 18px; border-radius: 12px; margin: 15px 0; font-size: 13px; line-height: 1.8;">
                                    <div><strong>المسار:</strong> <span style="color: #38bdf8; font-family: monospace;">{method} {full_url}</span></div>
                                    <div><strong>المستخدم:</strong> {user_str}</div>
                                    <div><strong>عنوان IP:</strong> {ip or 'غير معروف'}</div>
                                    <div><strong>توقيت الخطأ:</strong> {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                                    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #334155;">
                                        <strong style="color: #f87171;">رسالة الخطأ البرمجي:</strong>
                                        <pre style="background: #090d16; color: #fda4af; padding: 12px; border-radius: 8px; overflow-x: auto; font-family: monospace; font-size: 11px; white-space: pre-wrap; margin-top: 6px;">{exc_msg}</pre>
                                    </div>
                                </div>
                                <div style="text-align: center; margin-top: 25px;">
                                    <a href="https://raqamiyatapp.com/control/" style="display: inline-block; background: #06b6d4; color: #0f172a; font-weight: bold; padding: 10px 22px; border-radius: 10px; text-decoration: none; font-size: 13px;">فتح لوحة التحكم للإشراف</a>
                                </div>
                            </div>
                            """
                            send_brevo_email(
                                to_email=su.email,
                                to_name=su.get_full_name() or "Admin",
                                subject=title,
                                html_content=email_html
                            )
                        except Exception as ex_mail:
                            logger.warning("Failed to send 500 error email to %s: %s", su.email, ex_mail)
        except Exception as e:
            logger.warning("Failed to dispatch 500 error notifications: %s", e)

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
