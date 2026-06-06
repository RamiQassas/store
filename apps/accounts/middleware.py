from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

class AccountStatusMiddleware:
    """
    Middleware to enforce account status (banned/suspended) and specific restrictions.
    Logs out users whose accounts are no longer active.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Check if account is active (not banned or suspended)
            if not request.user.is_account_active:
                logout(request)
                messages.error(request, "تم إيقاف حسابك أو حظره. يرجى التواصل مع الإدارة.")
                return redirect("site_login")

        response = self.get_response(request)
        return response
