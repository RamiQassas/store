import logging
import json
import re
import hashlib
from django.http import HttpResponsePermanentRedirect, HttpResponseForbidden, Http404
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.core.cache import cache
from django.utils import timezone
from django.db import models

logger = logging.getLogger(__name__)


class DomainRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()
        primary_domain = 'raqamiyatapp.com'
        
        if 'raqamiyat.onrender.com' in host:
            new_url = f"https://{primary_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)
            
        clean_host = host.split(':')[0]
        if clean_host == 'www.raqamiyatapp.com':
            new_url = f"https://{primary_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)

        return self.get_response(request)


# ══════════════════════════════════════════════════════════════════════════════
# ── REAL-TIME SECURITY INTRUSION DETECTION & FORENSICS ENGINE ──────────────────
# ══════════════════════════════════════════════════════════════════════════════

def get_client_ip(request):
    """Extract real client IP considering reverse proxies and Cloudflare."""
    meta = getattr(request, "META", {})
    cf_ip = meta.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip.strip()
    x_forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    x_real = meta.get("HTTP_X_REAL_IP")
    if x_real:
        return x_real.strip()
    return meta.get("REMOTE_ADDR", "unknown")


def report_security_intrusion(request, attack_category, matched_detail, is_critical=False):
    """
    Collects forensic telemetry, creates a high-priority SystemAuditLog entry,
    and records an in-app admin notification in the control panel.
    Strictly NO emails are sent to personal inboxes for automated internet scans.
    """
    try:
        ip = get_client_ip(request)
        path = getattr(request, "path", "unknown")
        method = getattr(request, "method", "GET")
        meta = getattr(request, "META", {})
        ua = meta.get("HTTP_USER_AGENT", "غير معروف")
        query_string = meta.get("QUERY_STRING", "")
        now_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S")

        user = getattr(request, "user", None)
        user_str = f"{user.email} (ID: {user.id})" if (user and user.is_authenticated) else "زائر مجهول (Anonymous / External Attacker)"

        # 1. Permanent Audit Log in Control Panel (/control/audit-logs/)
        forensics = {
            "ip": ip,
            "method": method,
            "path": path,
            "query_string": query_string[:500],
            "user_agent": ua[:300],
            "attack_category": attack_category,
            "matched_pattern": matched_detail[:300],
            "timestamp": now_str,
            "user": user_str,
            "referer": meta.get("HTTP_REFERER", "")[:250],
        }

        try:
            from apps.common.models import SystemAuditLog
            SystemAuditLog.objects.create(
                actor=user if (user and user.is_authenticated) else None,
                action_type="security_intrusion_blocked",
                description=f"🚨 تم رصد وحظر محاولة اختراق [{attack_category}] من IP: {ip} على [{method} {path}]",
                ip_address=ip if (ip and len(ip) <= 45) else None,
                reason=matched_detail[:500],
                metadata=forensics
            )
        except Exception as e_log:
            logger.warning(f"Could not write SystemAuditLog for intrusion: {e_log}")

        # 2. In-App Notification in Control Panel (Throttled: 1 per 30 minutes per IP/category)
        throttle_key_app = f"sec_inapp_alert_{hashlib.md5(f'{ip}_{attack_category}'.encode()).hexdigest()}"
        if not cache.get(throttle_key_app):
            cache.set(throttle_key_app, True, 1800)
            try:
                from django.contrib.auth import get_user_model
                from apps.notifications.models import Notification

                User = get_user_model()
                admins = User.objects.filter(
                    models.Q(is_superuser=True) | models.Q(is_staff=True),
                    is_active=True
                ).distinct()

                notif_title = f"🚨 تم صد محاولة اختراق: {attack_category}"
                notif_body = (
                    f"تم حظر هجوم إلكتروني بنجاح.\n"
                    f"نوع التهديد: {attack_category}\n"
                    f"النمط المكتشف: {matched_detail[:150]}\n"
                    f"عنوان IP: {ip}\n"
                    f"المسار المستهدف: {method} {path}\n"
                    f"المتصفح/الأداة: {ua[:120]}\n"
                    f"التوقيت: {now_str}"
                )

                for adm in admins:
                    try:
                        Notification.objects.create(
                            user=adm,
                            title=notif_title,
                            body=notif_body,
                            action_url="/control/audit-logs/",
                            channel=Notification.Channel.IN_APP,
                            priority=Notification.Priority.HIGH,
                            metadata=forensics
                        )
                    except Exception:
                        pass
            except Exception as e_notif:
                logger.warning(f"Failed to create intrusion in-app notification: {e_notif}")

    except Exception as e_main:
        logger.error(f"Error in report_security_intrusion: {e_main}")


class SecurityIntrusionDetectionMiddleware:
    """
    Real-time Web Application Security & Intrusion Detection Middleware.
    Inspects incoming requests for malicious payloads (SQLi, Path Traversal,
    Exploit Probes, Remote Code Execution, Suspicious Scanner User-Agents).
    Automatically bans attacker IPs for 24 hours in cache and drops malicious traffic with 403 Forbidden.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = get_client_ip(request)
        ban_key = f"sec_banned_ip_{hashlib.md5(ip.encode()).hexdigest()}"

        # Fast drop: If this IP is already banned for probing, drop immediately with zero DB overhead
        if cache.get(ban_key):
            return HttpResponseForbidden("Access Denied.")

        path = str(request.path or "").lower()
        meta = getattr(request, "META", {})
        query_str = meta.get("QUERY_STRING", "").lower()
        combined = f"{path}?{query_str}"
        ua = meta.get("HTTP_USER_AGENT", "").lower()

        def block_and_ban(category, detail, is_critical=False):
            # Ban attacker IP for 24 hours in cache
            cache.set(ban_key, True, 86400)
            report_security_intrusion(request, category, detail, is_critical=is_critical)
            return HttpResponseForbidden("Access Denied: Malicious probe detected and blocked.")

        # 1. Sensitive Configuration & Secret Files Probing
        SENSITIVE_FILES = (
            "/.env", "/.git", "/.svn", "/.htaccess", "/.htpasswd", "/web.config",
            "/config.json", "/database.yml", "/secrets.yml", "/id_rsa", "/id_dsa",
            "/docker-compose.yml", "/wp-config.php", "/dump.sql", "/backup.sql"
        )
        for sf in SENSITIVE_FILES:
            if sf in path:
                return block_and_ban("محاولة استكشاف ملفات حساسة (ماسح آلي)", f"طلب المسار الحساس: {path}", is_critical=False)

        # 2. Known Web Shells, CMS & Vulnerability Exploits
        EXPLOIT_PATHS = (
            "wp-login.php", "xmlrpc.php", "phpmyadmin", "/pma", "/adminer", "setup.cgi",
            "boaform", "/hnap", "shell.php", "eval.php", "c99.php", "r57.php", "wso.php",
            "alfa.php", "actuator/heapdump", "actuator/env", "solr/admin", "telescope/requests"
        )
        for ep in EXPLOIT_PATHS:
            if ep in path:
                return block_and_ban("محاولة استكشاف مسارات اختراق خارجية (ماسح آلي)", f"محاولة طلب: {path}", is_critical=False)

        # 3. Path Traversal & Local File Inclusion (LFI)
        TRAVERSAL_PATTERNS = (
            "../", "..\\", "%2e%2e", "/etc/passwd", "/etc/shadow", "c:\\windows\\system32", "win.ini"
        )
        for tp in TRAVERSAL_PATTERNS:
            if tp in combined:
                return block_and_ban("محاولة اختراق تخطي المسارات (Directory Traversal / LFI)", f"النمط المرصود: {tp} في الرابط {combined}", is_critical=True)

        # 4. SQL Injection Attack Signatures
        SQLI_PATTERNS = (
            "union select", "union+select", "' union ",
            "information_schema", "benchmark(", "pg_sleep", "waitfor delay",
            "' or '1'='1", "' or 1=1", "admin' --", "' or ''='"
        )
        for sqli in SQLI_PATTERNS:
            if sqli in combined:
                return block_and_ban("محاولة حقن قواعد البيانات (SQL Injection Attack)", f"الرمز المرصود: {sqli} في {combined}", is_critical=True)

        # 5. Remote Command Execution / Log4j
        RCE_PATTERNS = (
            "${jndi:", ";cat /etc/", "|cat /etc/", "cmd.exe", "/bin/sh", "/bin/bash", "powershell.exe"
        )
        for rce in RCE_PATTERNS:
            if rce in combined:
                return block_and_ban("محاولة تنفيذ أوامر عن بعد (Remote Code Execution / RCE)", f"الحمولة المرصودة: {rce} في {combined}", is_critical=True)

        # 6. Malicious Automated Vulnerability Scanner User-Agents
        SCANNER_AGENTS = (
            "sqlmap", "nikto", "wpscan", "gobuster", "dirbuster", "masscan",
            "zgrab", "acunetix", "openvas", "nessus", "metasploit"
        )
        for sa in SCANNER_AGENTS:
            if sa in ua:
                return block_and_ban("أداة فحص واختراق آلية محظورة (Security Scanner Bot)", f"اسم الأداة: {ua}", is_critical=False)

        return self.get_response(request)


# ══════════════════════════════════════════════════════════════════════════════
# ── UNHANDLED 500 SERVER ERROR NOTIFIER ───────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def is_scanner_or_exploit_probe(request, path, exc_msg):
    """Detects automated bot scanners, exploit probes, and malicious crawler requests."""
    path_lower = str(path or "").lower()
    meta = getattr(request, "META", {})
    ua = meta.get("HTTP_USER_AGENT", "").lower()
    
    SUSPICIOUS_EXTENSIONS = (
        ".php", ".asp", ".aspx", ".jsp", ".cgi", ".env", ".git", ".yaml", ".yml",
        ".bak", ".sql", ".tar", ".gz", ".rar", ".zip", ".ini", ".conf", ".cfg"
    )
    if any(path_lower.endswith(ext) or (ext + "/") in path_lower or (ext + "?") in path_lower for ext in SUSPICIOUS_EXTENSIONS):
        return True

    SUSPICIOUS_PATHS = (
        "wp-", "wordpress", "phpmyadmin", "pma", "cgi-bin", "boaform", "hnap",
        "actuator", "solr", "setup.cgi", "console", "telescope", "debug",
        ".well-known", "autodiscover", "owa", "exchange", "invoker", "jmx-console"
    )
    if any(sp in path_lower for sp in SUSPICIOUS_PATHS):
        return True

    query_str = meta.get("QUERY_STRING", "").lower()
    combined = f"{path_lower}?{query_str}"
    EXPLOIT_PATTERNS = (
        "../", "..\\", "%2e%2e", "<script", "%3cscript", "union+select", "select+",
        "information_schema", "benchmark(", "sleep(", "waitfor+delay", "order+by+",
        "etc/passwd", "win.ini", "eval(", "base64_decode"
    )
    if any(ep in combined for ep in EXPLOIT_PATTERNS):
        return True

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
    whenever a genuine unhandled 500 error occurs. No emails are sent to avoid inbox spam.
    """
    try:
        path = getattr(request, "path", "unknown")
        method = getattr(request, "method", "GET")
        user = getattr(request, "user", None)
        user_str = f"{user.email} (ID: {user.id})" if user and user.is_authenticated else "زائر غير مسجل (Anonymous)"

        ip = get_client_ip(request)
        exc_msg = str(exception) if exception else "خطأ غير متوقع في الخادم (500 Internal Server Error)"

        # Check if this is an automated bot probe or exploit scan
        if is_scanner_or_exploit_probe(request, path, exc_msg):
            return

        raw_key_seed = f"{path}_{method}_{exc_msg[:50]}".encode("utf-8")
        throttle_key = f"err_notify_{hashlib.md5(raw_key_seed).hexdigest()}"
        if cache.get(throttle_key):
            return
        cache.set(throttle_key, True, 300)

        # 1. Audit Log in Control Panel
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
            logger.warning(f"Failed to create SystemAuditLog for 500 error: {e}")

        # 2. In-App Notification for Admins in Control Panel
        try:
            from django.contrib.auth import get_user_model
            from apps.notifications.models import Notification
            
            User = get_user_model()
            admins = User.objects.filter(
                models.Q(is_superuser=True) | models.Q(is_staff=True),
                is_active=True
            ).distinct()

            full_url = request.get_full_path() if hasattr(request, "get_full_path") else path
            title = f"⚠️ تنبيه: خطأ في الخادم (500) على المسار {path[:45]}"
            body = (
                f"المستخدم: {user_str}\n"
                f"المسار: {method} {full_url}\n"
                f"عنوان IP: {ip}\n"
                f"الخطأ: {exc_msg[:250]}\n"
                f"الوقت: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            for adm in admins:
                try:
                    Notification.objects.create(
                        user=adm,
                        title=title,
                        body=body,
                        action_url=path if path.startswith("/") else "/control/",
                        channel=Notification.Channel.IN_APP,
                        priority=Notification.Priority.HIGH,
                        metadata={
                            "path": path,
                            "method": method,
                            "user": user_str,
                            "ip": ip,
                            "error": exc_msg[:300]
                        }
                    )
                except Exception as ex_adm:
                    logger.warning(f"Failed to notify admin {getattr(adm, 'email', adm)}: {ex_adm}")

        except Exception as e:
            logger.warning(f"Failed to dispatch 500 error notifications: {e}")

    except Exception as e:
        logger.error(f"Error in record_server_error_and_notify: {e}")


class ServerErrorNotificationMiddleware:
    """
    Middleware that intercepts exceptions and notifies administrators in real-time in the control panel.
    Safely ignores normal HTTP 403, 404, and expected model lookups.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 500:
            record_server_error_and_notify(request, status_code=response.status_code)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, (PermissionDenied, Http404, ObjectDoesNotExist)):
            return None
        record_server_error_and_notify(request, exception=exception, status_code=500)
        return None
