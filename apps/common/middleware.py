import logging
import threading
import json
import re
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
    creates in-app admin alert, and dispatches an instant email to the owner.
    Guaranteed non-blocking: dispatches email asynchronously in a background thread.
    """
    try:
        ip = get_client_ip(request)
        path = getattr(request, "path", "unknown")
        method = getattr(request, "method", "GET")
        meta = getattr(request, "META", {})
        ua = meta.get("HTTP_USER_AGENT", "غير معروف")
        query_string = meta.get("QUERY_STRING", "")
        full_url = request.get_full_path() if hasattr(request, "get_full_path") else path
        now_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S")

        user = getattr(request, "user", None)
        user_str = f"{user.email} (ID: {user.id})" if (user and user.is_authenticated) else "زائر مجهول (Anonymous / External Attacker)"

        # 1. Permanent Audit Log with full forensics
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

        # 2. In-App Notification (Throttled: 1 per 3 minutes per IP)
        import hashlib
        throttle_key_app = f"sec_inapp_alert_{hashlib.md5(f'{ip}_{attack_category}'.encode()).hexdigest()}"
        if not cache.get(throttle_key_app):
            cache.set(throttle_key_app, True, 180)
            try:
                from django.contrib.auth import get_user_model
                from apps.notifications.models import Notification
                from apps.notifications.services import notify_user

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
                        notify_user(
                            user=adm,
                            title=notif_title,
                            body=notif_body,
                            action_url="/control/audit-logs/",
                            category="security",
                            priority=Notification.Priority.URGENT,
                            metadata=forensics
                        )
                    except Exception:
                        pass
            except Exception as e_notif:
                logger.warning(f"Failed to create intrusion in-app notification: {e_notif}")

        # 2.5 Track repeat attacks per IP
        ip_attack_count_key = f"sec_ip_atk_cnt_{hashlib.md5(ip.encode()).hexdigest()}"
        attack_count = cache.get(ip_attack_count_key, 0) + 1
        cache.set(ip_attack_count_key, attack_count, 600)

        # 3. Direct Email Alert to Owner
        # Only email on critical threats (SQLi/RCE) OR persistent attackers (>= 4 attacks in 10 mins).
        # Routine internet scanner bots (dump.sql, .git, etc.) are blocked and logged silently.
        should_send_email = is_critical or (attack_count >= 4)
        global_email_throttle_key = "sec_global_email_alert_throttle"
        email_ip_throttle_key = f"sec_email_alert_{hashlib.md5(f'{ip}_{attack_category}'.encode()).hexdigest()}"

        can_send_email = (
            should_send_email
            and not bool(cache.get(global_email_throttle_key))
            and not bool(cache.get(email_ip_throttle_key))
        )
        if can_send_email:
            cache.set(global_email_throttle_key, True, 900)  # 15 minutes global throttle
            cache.set(email_ip_throttle_key, True, 1800)     # 30 minutes per IP/category

            def _send_intrusion_email():
                try:
                    from apps.accounts.services import send_brevo_email
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    superusers = User.objects.filter(is_superuser=True, is_active=True)
                    recipient_emails = [su.email for su in superusers if getattr(su, "email", None)]
                    if "ramiqassas2002@gmail.com" not in recipient_emails:
                        recipient_emails.append("ramiqassas2002@gmail.com")

                    email_html = f"""
                    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; max-width: 650px; margin: 0 auto; background: #0b132b; color: #f8fafc; padding: 25px; border-radius: 16px; border: 2px solid #ef4444; box-shadow: 0 10px 30px rgba(239,68,68,0.2);">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px; border-bottom: 1px solid #1e293b; padding-bottom: 15px;">
                            <span style="font-size: 28px;">🚨</span>
                            <div>
                                <h2 style="color: #ef4444; margin: 0; font-size: 20px;">إنذار أمني فوري: تم رصد وحظر محاولة اختراق</h2>
                                <span style="font-size: 12px; color: #94a3b8;">نظام الحماية الذكي في موقع رقميات (Raqamiyat Security Barrier)</span>
                            </div>
                        </div>

                        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                            تم اعتراض وحظر محاولة وصول خبيثة مشبوهة تستهدف استكشاف أو استغلال ثغرات في الموقع. إليك التفاصيل الجنائية الكاملة للعملية:
                        </p>

                        <div style="background: #1c2541; padding: 18px; border-radius: 12px; margin: 15px 0; font-size: 13px; line-height: 1.9; border: 1px solid #334155;">
                            <div><strong style="color: #f87171;">تصنيف التهديد:</strong> <span style="background: rgba(239,68,68,0.2); color: #fca5a5; padding: 2px 8px; border-radius: 6px; font-weight: bold;">{attack_category}</span></div>
                            <div><strong style="color: #38bdf8;">عنوان IP المهاجم:</strong> <code style="background: #090d16; color: #38bdf8; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{ip}</code></div>
                            <div><strong>المسار المستهدف:</strong> <code style="color: #fbbf24; font-family: monospace;">{method} {full_url}</code></div>
                            <div><strong>المستخدم:</strong> {user_str}</div>
                            <div><strong>توقيت الرصد:</strong> {now_str}</div>
                            <div><strong>أداة / متصفح المهاجم (User-Agent):</strong> <div style="color: #94a3b8; font-family: monospace; font-size: 11px; word-break: break-all; margin-top: 2px;">{ua}</div></div>
                            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #334155;">
                                <strong style="color: #fca5a5;">النمط / الحمولة المرصودة:</strong>
                                <pre style="background: #090d16; color: #f87171; padding: 10px; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 12px; margin-top: 5px; white-space: pre-wrap;">{matched_detail}</pre>
                            </div>
                        </div>

                        <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 12px; font-size: 12px; color: #6ee7b7; margin-bottom: 20px;">
                            🛡️ <strong>إجراء الحماية المتخذ:</strong> تم صد الطلب فوراً برمز الاستجابة 403 Forbidden وإلغاء تنفيذ أي أوامر أو استعلامات برمجية، وتوثيق سجل الهجوم في قاعدة البيانات.
                        </div>

                        <div style="text-align: center;">
                            <a href="https://raqamiyatapp.com/control/audit-logs/" style="display: inline-block; background: #ef4444; color: #ffffff; font-weight: bold; padding: 10px 24px; border-radius: 10px; text-decoration: none; font-size: 13px;">فتح سجل التدقيق الأمني في لوحة التحكم</a>
                        </div>
                    </div>
                    """
                    for email in recipient_emails:
                        try:
                            send_brevo_email(
                                to_email=email,
                                to_name="مدير نظام رقميات",
                                subject=f"🚨 إنذار أمني فوري: تم رصد وحظر محاولة اختراق [{attack_category}]",
                                html_content=email_html
                            )
                        except Exception as ex_mail:
                            logger.warning(f"Failed to send intrusion email to {email}: {ex_mail}")
                except Exception as e_th:
                    logger.error(f"Error in intrusion email worker thread: {e_th}")

            threading.Thread(target=_send_intrusion_email, daemon=True).start()

    except Exception as e_main:
        logger.error(f"Error in report_security_intrusion: {e_main}")


class SecurityIntrusionDetectionMiddleware:
    """
    Real-time Web Application Security & Intrusion Detection Middleware.
    Inspects incoming requests for malicious payloads (SQLi, Path Traversal,
    Exploit Probes, Remote Code Execution, Suspicious Scanner User-Agents).
    Logs full forensic telemetry and immediately alerts the site owner.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = str(request.path or "").lower()
        meta = getattr(request, "META", {})
        query_str = meta.get("QUERY_STRING", "").lower()
        combined = f"{path}?{query_str}"
        ua = meta.get("HTTP_USER_AGENT", "").lower()

        # 1. Sensitive Configuration & Secret Files Probing
        SENSITIVE_FILES = (
            "/.env", "/.git", "/.svn", "/.htaccess", "/.htpasswd", "/web.config",
            "/config.json", "/database.yml", "/secrets.yml", "/id_rsa", "/id_dsa",
            "/docker-compose.yml", "/wp-config.php", "/dump.sql", "/backup.sql"
        )
        for sf in SENSITIVE_FILES:
            if sf in path:
                report_security_intrusion(request, "محاولة استكشاف ملفات حساسة (ماسح آلي)", f"طلب المسار الحساس: {path}", is_critical=False)
                return HttpResponseForbidden("Access Denied: Unauthorized security probe detected and logged.")

        # 2. Known Web Shells, CMS & Vulnerability Exploits
        EXPLOIT_PATHS = (
            "wp-login.php", "xmlrpc.php", "phpmyadmin", "/pma", "/adminer", "setup.cgi",
            "boaform", "/hnap", "shell.php", "eval.php", "c99.php", "r57.php", "wso.php",
            "alfa.php", "actuator/heapdump", "actuator/env", "solr/admin", "telescope/requests"
        )
        for ep in EXPLOIT_PATHS:
            if ep in path:
                report_security_intrusion(request, "محاولة استكشاف مسارات اختراق خارجية (ماسح آلي)", f"محاولة طلب: {path}", is_critical=False)
                return HttpResponseForbidden("Access Denied: Malicious probe detected and logged.")

        # 3. Path Traversal & Local File Inclusion (LFI)
        TRAVERSAL_PATTERNS = (
            "../", "..\\", "%2e%2e", "/etc/passwd", "/etc/shadow", "c:\\windows\\system32", "win.ini"
        )
        for tp in TRAVERSAL_PATTERNS:
            if tp in combined:
                report_security_intrusion(request, "محاولة اختراق تخطي المسارات (Directory Traversal / LFI)", f"النمط المرصود: {tp} في الرابط {combined}", is_critical=True)
                return HttpResponseForbidden("Access Denied: Path traversal detected and logged.")

        # 4. SQL Injection Attack Signatures
        SQLI_PATTERNS = (
            "union select", "union+select", "' union ",
            "information_schema", "benchmark(", "pg_sleep", "waitfor delay",
            "' or '1'='1", "' or 1=1", "admin' --", "' or ''='"
        )
        for sqli in SQLI_PATTERNS:
            if sqli in combined:
                report_security_intrusion(request, "محاولة حقن قواعد البيانات (SQL Injection Attack)", f"الرمز المرصود: {sqli} في {combined}", is_critical=True)
                return HttpResponseForbidden("Access Denied: SQL injection detected and logged.")

        # 5. Remote Command Execution / Log4j
        RCE_PATTERNS = (
            "${jndi:", ";cat /etc/", "|cat /etc/", "cmd.exe", "/bin/sh", "/bin/bash", "powershell.exe"
        )
        for rce in RCE_PATTERNS:
            if rce in combined:
                report_security_intrusion(request, "محاولة تنفيذ أوامر عن بعد (Remote Code Execution / RCE)", f"الحمولة المرصودة: {rce} في {combined}")
                return HttpResponseForbidden("Access Denied: Command injection detected and logged.")

        # 6. Malicious Automated Vulnerability Scanner User-Agents
        SCANNER_AGENTS = (
            "sqlmap", "nikto", "wpscan", "gobuster", "dirbuster", "masscan",
            "zgrab", "acunetix", "openvas", "nessus", "metasploit"
        )
        for sa in SCANNER_AGENTS:
            if sa in ua:
                report_security_intrusion(request, "أداة فحص واختراق آلية محظورة (Security Scanner Bot)", f"اسم الأداة: {ua}")
                return HttpResponseForbidden("Access Denied: Automated vulnerability scanner blocked.")

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
    whenever a genuine unhandled 500 error occurs. Dispatches emails asynchronously.
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

        import hashlib
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

        # 2. Multi-channel Notification for Admins
        try:
            from django.contrib.auth import get_user_model
            from apps.notifications.models import Notification
            from apps.notifications.services import notify_user
            
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
                    logger.warning(f"Failed to notify admin {getattr(adm, 'email', adm)}: {ex_adm}")

            # Asynchronous email dispatch to avoid worker blocking
            email_throttle_key = "admin_500_email_hourly_throttle"
            can_send_email = not bool(cache.get(email_throttle_key))
            if can_send_email:
                cache.set(email_throttle_key, True, 3600)
                superusers = list(admins.filter(is_superuser=True))

                def _send_500_email():
                    from apps.accounts.services import send_brevo_email
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
                                        <div><strong>عنوان IP:</strong> {ip}</div>
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
                                logger.warning(f"Failed to send 500 error email to {su.email}: {ex_mail}")

                threading.Thread(target=_send_500_email, daemon=True).start()

        except Exception as e:
            logger.warning(f"Failed to dispatch 500 error notifications: {e}")

    except Exception as e:
        logger.error(f"Error in record_server_error_and_notify: {e}")


class ServerErrorNotificationMiddleware:
    """
    Middleware that intercepts exceptions and notifies administrators in real-time.
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
