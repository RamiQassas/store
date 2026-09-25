from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.sessions.models import Session
import logging
from apps.accounts.models import KYCSettings, KYCRequest

logger = logging.getLogger(__name__)

class AccountStatusMiddleware:
    """
    Middleware to enforce account status (banned/suspended) and specific restrictions.
    Also enforces single session login (concurrent session control) and country-based blocks.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # 1. Check if account is active (not banned or suspended)
            if not request.user.is_account_active:
                logger.info("Inactive account rejected for user=%s", request.user.pk)
                logout(request)
                messages.error(request, "تم إيقاف حسابك أو حظره. يرجى التواصل مع الإدارة.")
                return redirect("site_login")
            
            # 2. Check Session Inactivity Timeout (1 week = 7 days)
            from django.utils import timezone
            from django.conf import settings
            session_idle_timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 7 * 24 * 3600)
            now_ts = timezone.now().timestamp()
            last_activity = request.session.get("last_activity")
            if last_activity:
                try:
                    idle_seconds = now_ts - float(last_activity)
                    if idle_seconds > session_idle_timeout:
                        logger.info("Session expired due to inactivity for user=%s (idle %ss)", request.user.pk, int(idle_seconds))
                        logout(request)
                        messages.info(request, "تم تسجيل خروجك تلقائياً لمرور أكثر من أسبوع دون نشاط، وذلك لحماية أمان حسابك.")
                        return redirect("site_login")
                except Exception:
                    pass
            request.session["last_activity"] = now_ts

            # 3. Enforce Single Active Session (One Device at a time)
            current_scope = str(request.store.pk) if getattr(request, "store", None) else "main"
            if request.session.get("session_scope") != current_scope:
                request.session["session_scope"] = current_scope

            skip_single_session = (
                request.user.is_superuser
                or request.user.is_staff
                or getattr(request.user, "role", None) in [
                    "super_admin",
                    "admin",
                    "support",
                    "finance",
                    "moderator",
                ]
                or getattr(request, "store", None) is not None
            )
            if not skip_single_session:
                curr_key = request.session.session_key
                user_key = request.user.last_session_key
                if user_key and curr_key and user_key != curr_key:
                    # Current device's session was superseded by a login from another device
                    logger.info("Session superseded: session %s != user.last_session_key %s for user=%s", curr_key, user_key, request.user.pk)
                    logout(request)
                    messages.warning(request, "تم تسجيل الدخول إلى حسابك من جهاز آخر. تم إنهاء هذه الجلسة تلقائياً لحماية أمان حسابك.")
                    return redirect("site_login")
                elif curr_key and not user_key:
                    # Sync initial session key
                    request.user.last_session_key = curr_key
                    request.user.save(update_fields=["last_session_key"])

            # 3. Country-Based Block (Compliance)
            # Skip for staff/admin
            if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, "role", None) in ["super_admin", "admin"]):
                kyc_settings = KYCSettings.get_settings()
                restricted = kyc_settings.restricted_countries or []
                if restricted:
                    is_blocked = False
                    user_country = request.user.last_country # ISO code or Name from IP Geolocation
                    
                    # Check KYC country if verified
                    kyc_country = None
                    if request.user.is_kyc_verified:
                        kyc = KYCRequest.objects.filter(user=request.user, status=KYCRequest.Status.APPROVED).first()
                        if kyc:
                            kyc_country = kyc.issuing_country
                    
                    # Logic: If user's logged country OR KYC country is in restricted list
                    if user_country in restricted or kyc_country in restricted:
                        is_blocked = True
                    
                    if is_blocked:
                        # Allow access ONLY to specific pages (like support) if needed, 
                        # but usually we block the whole dashboard.
                        logout(request)
                        messages.error(request, "عذراً، دولتك غير مدعومة حالياً وفقاً لسياسات الامتثال. لسحب أرصدتكم يرجى التواصل مع الدعم الفني.")
                        return redirect("site_login")

        response = self.get_response(request)
        return response
