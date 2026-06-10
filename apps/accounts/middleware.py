from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.sessions.models import Session

class AccountStatusMiddleware:
    """
    Middleware to enforce account status (banned/suspended) and specific restrictions.
    Also enforces single session login (concurrent session control).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # 1. Check if account is active (not banned or suspended)
            if not request.user.is_account_active:
                logout(request)
                messages.error(request, "تم إيقاف حسابك أو حظره. يرجى التواصل مع الإدارة.")
                return redirect("site_login")
            
            # 2. Enforce Single Session Login
            # If the user's recorded last_session_key is different from current,
            # it means they logged in elsewhere.
            # We skip this check for staff/admin to avoid disrupting support work
            if not request.user.is_staff and request.user.last_session_key:
                if request.user.last_session_key != request.session.session_key:
                    logout(request)
                    messages.warning(request, "تم تسجيل الدخول من جهاز آخر. تم إنهاء الجلسة الحالية.")
                    return redirect("site_login")

        response = self.get_response(request)
        return response
