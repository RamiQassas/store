from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.sessions.models import Session
from apps.accounts.models import KYCSettings, KYCRequest

class AccountStatusMiddleware:
    """
    Middleware to enforce account status (banned/suspended) and specific restrictions.
    Also enforces single session login (concurrent session control) and country-based blocks.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            print(f"[AccountStatusMiddleware] Checking user: {request.user.email}, is_active: {request.user.is_active}, is_account_active: {request.user.is_account_active}, last_session_key: {request.user.last_session_key}, current_session_key: {request.session.session_key}")
            # 1. Check if account is active (not banned or suspended)
            if not request.user.is_account_active:
                print(f"[AccountStatusMiddleware] User {request.user.email} is not active. Logging out.")
                logout(request)
                messages.error(request, "تم إيقاف حسابك أو حظره. يرجى التواصل مع الإدارة.")
                return redirect("site_login")
            
            # 2. Enforce Single Session Login
            if not request.user.is_staff:
                if request.user.last_session_key:
                    if request.session.session_key and request.user.last_session_key != request.session.session_key:
                        print(f"[AccountStatusMiddleware] Session mismatch! User last_session_key: {request.user.last_session_key}, Current: {request.session.session_key}. Logging out.")
                        logout(request)
                        messages.warning(request, "تم تسجيل الدخول من جهاز آخر. تم إنهاء الجلسة الحالية.")
                        return redirect("site_login")
                elif request.session.session_key:
                    # Sync initial session key
                    request.user.last_session_key = request.session.session_key
                    request.user.save(update_fields=["last_session_key"])

            # 3. Country-Based Block (Compliance)
            # Skip for staff/admin
            if not request.user.is_staff:
                kyc_settings = KYCSettings.get_settings()
                restricted = kyc_settings.restricted_countries or []
                print(f"[AccountStatusMiddleware] Restricted countries: {restricted}, User country: {request.user.last_country}")
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
