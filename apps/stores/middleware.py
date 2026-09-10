import re
import time
from urllib.parse import urlparse
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date

from apps.stores.models import Store, StoreEmployee
from apps.common.tenant_utils import (
    set_current_store,
    reset_current_store,
    _bypass_tenant_filter,
    bypass_tenant_filter
)


def get_clean_subdomain_cookie_suffix(subdomain):
    """
    Sanitize subdomain string to be safe as a cookie name suffix (RFC 6265 compliant).
    """
    if not subdomain:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', str(subdomain).lower())
    return clean[:32]


class TenantResolutionMiddleware:
    """
    Runs FIRST in the middleware pipeline (before Session and Auth).
    Resolves request.store from the host, sets request.urlconf for tenant routing,
    and initializes the threadlocal tenant context.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass tenant filter for all django-allauth requests
        if request.path.startswith('/accounts/'):
            token = _bypass_tenant_filter.set(True)
            request._bypass_token = token

        # 1. Get host name from request
        host = request.get_host().split(':')[0].lower()

        # 2. Determine main domain
        site_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
        main_domain = urlparse(site_url).hostname or "raqamiyatapp.com"
        main_domain = main_domain.lower()
        if main_domain.startswith("www."):
            main_domain = main_domain[4:]

        # Build list of main domains we support
        main_domains = [main_domain]
        if "onrender.com" in host:
            parts = host.split('.')
            if len(parts) >= 3:
                main_domains.append(".".join(parts[-3:]))
            else:
                main_domains.append(host)

        # 3. Check if host matches main domain or subdomain
        request.store = None
        is_subdomain = False
        subdomain = ""

        # Check against each configured main domain
        for m_domain in main_domains:
            cleaned_m_domain = m_domain[4:] if m_domain.startswith("www.") else m_domain
            if host.endswith("." + cleaned_m_domain) and host != cleaned_m_domain:
                subdomain = host[:-(len(cleaned_m_domain) + 1)]
                is_subdomain = True
                if subdomain == "www":
                    is_subdomain = False
                break

        if not is_subdomain and main_domain in ["localhost", "127.0.0.1", "testserver"]:
            parts = host.split('.')
            if len(parts) > 1 and parts[-1] in ["localhost", "127", "testserver"]:
                subdomain = parts[0]
                is_subdomain = True

        if is_subdomain:
            try:
                with bypass_tenant_filter():
                    store = Store.objects.get(subdomain__iexact=subdomain)

                # Check subscription expiration
                from django.utils import timezone
                if store.subscription_end and store.subscription_end < timezone.now():
                    with bypass_tenant_filter():
                        if store.auto_renew:
                            renewed = store.renew_subscription()
                            if not renewed:
                                store.subscription_status = Store.Status.SUSPENDED
                                store.is_active = False
                                store.save()
                        else:
                            store.subscription_status = Store.Status.SUSPENDED
                            store.is_active = False
                            store.save()

                if not store.is_active:
                    return HttpResponseForbidden("<h1>المتجر موقوف مؤقتاً</h1><p>هذا المتجر تم إيقافه مؤقتاً من قبل إدارة المنصة.</p>")
                request.store = store
            except Store.DoesNotExist:
                raise Http404("المتجر المطلوب غير موجود.")
            except Exception as e:
                print(f"[TenantResolutionMiddleware] Error during subdomain lookup: {str(e)}")
        else:
            # Check for custom domains
            is_main_domain_or_local = (host in main_domains) or (host in ["localhost", "127.0.0.1", "testserver"]) or any(host.endswith("." + d) for d in main_domains)
            if not is_main_domain_or_local:
                try:
                    with bypass_tenant_filter():
                        store = Store.objects.filter(custom_domain=host).first()
                    if store:
                        if not store.is_active:
                            return HttpResponseForbidden("<h1>المتجر موقوف مؤقتاً</h1><p>هذا المتجر تم إيقافه مؤقتاً من قبل إدارة المنصة.</p>")
                        request.store = store
                    else:
                        raise Http404("هذا النطاق غير مرتبط بأي متجر على المنصة.")
                except Http404:
                    raise
                except Exception as e:
                    print(f"[TenantResolutionMiddleware] Error during custom domain lookup: {str(e)}")

        # 4. Bind tenant routing and threadlocal context
        if request.store:
            request.urlconf = 'apps.stores.urls'
            token = set_current_store(request.store)
            request._tenant_token = token

        try:
            response = self.get_response(request)
        finally:
            # Clean up context variables to prevent thread leaking
            if hasattr(request, '_tenant_token'):
                reset_current_store(request._tenant_token)
            if hasattr(request, '_bypass_token'):
                _bypass_tenant_filter.reset(request._bypass_token)

        return response


class TenantSessionMiddleware(SessionMiddleware):
    """
    Tenant-aware SessionMiddleware.
    Dynamically isolates the session cookie name per store:
    - Main platform uses settings.SESSION_COOKIE_NAME ('sessionid')
    - Tenant stores use 'sessionid_<clean_subdomain>'
    Ensures complete cookie isolation in browsers across stores and main platform tabs.
    """
    def get_cookie_name(self, request):
        store = getattr(request, 'store', None)
        if store and getattr(store, 'subdomain', None):
            suffix = get_clean_subdomain_cookie_suffix(store.subdomain)
            if suffix:
                return f"sessionid_{suffix}"
        return settings.SESSION_COOKIE_NAME

    def process_request(self, request):
        cookie_name = self.get_cookie_name(request)
        request._tenant_session_cookie_name = cookie_name
        session_key = request.COOKIES.get(cookie_name)
        if not session_key and cookie_name != settings.SESSION_COOKIE_NAME:
            # Fallback for clients (e.g. Django test client / force_login) that only set standard sessionid
            session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(session_key)

    def process_response(self, request, response):
        cookie_name = getattr(request, '_tenant_session_cookie_name', None) or self.get_cookie_name(request)
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            return response

        # If the session is empty, delete the tenant-scoped session cookie
        if cookie_name in request.COOKIES and empty:
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            patch_vary_headers(response, ("Cookie",))
        else:
            if accessed:
                patch_vary_headers(response, ("Cookie",))
            if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires_time = time.time() + max_age
                    expires = http_date(expires_time)

                if response.status_code < 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        raise SessionInterrupted(
                            "The request's session was deleted before the "
                            "request completed. The user may have logged "
                            "out in a concurrent request, for example."
                        )
                    response.set_cookie(
                        cookie_name,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=settings.SESSION_COOKIE_DOMAIN,
                        path=settings.SESSION_COOKIE_PATH,
                        secure=settings.SESSION_COOKIE_SECURE or None,
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
        return response


class TenantSecurityMiddleware:
    """
    Runs AFTER AuthenticationMiddleware.
    Enforces tenant access rules strictly without flushing sessions:
    - If user belongs to another store: sets request.user = AnonymousUser()
      (NEVER calls logout(request) to avoid deleting session rows from django_session)
    - If user tries to access protected views without permission: redirects to login
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            if request.store:
                if not self._user_belongs_to_store(request.user, request.store):
                    # Alien session presented: decouple user from request context WITHOUT destroying the session
                    request.user = AnonymousUser()
                    if request.path.startswith(("/dashboard/", "/merchant/")):
                        return HttpResponseRedirect("/auth/login/")
            else:
                # Main site
                is_staff_or_admin = (
                    request.user.is_superuser
                    or request.user.is_staff
                    or getattr(request.user, "role", None) == "super_admin"
                )
                if is_staff_or_admin:
                    if request.path.startswith('/admin/') or request.path.startswith('/control/'):
                        token = _bypass_tenant_filter.set(True)
                        request._bypass_token = token
                else:
                    # Strict isolation: regular sub-store customers cannot access main site dashboard
                    next_url_val = str(request.GET.get('next', '')) or str(request.session.get('next', ''))
                    is_sso = request.path.startswith('/auth/sso-callback/') or (
                        request.path.startswith('/accounts/') and 'sso-callback' in next_url_val
                    )
                    if not is_sso:
                        if getattr(request.user, "store_id", None) is not None:
                            with bypass_tenant_filter():
                                is_owner = request.user.owned_stores.exists()
                            if not is_owner:
                                # Sub-store customer accessing main platform: decouple without destroying DB session
                                request.user = AnonymousUser()
                                if request.path.startswith(("/dashboard/", "/control/")):
                                    return HttpResponseRedirect("/auth/login/")

        return self.get_response(request)

    def _user_belongs_to_store(self, user, store):
        if user.is_superuser or user.is_staff or getattr(user, "role", None) == "super_admin":
            return True

        if getattr(user, "store_id", None) is None:
            # Main platform users can access and purchase from sub-stores
            return True

        with bypass_tenant_filter():
            user_store_id = str(user.store_id) if user.store_id else None
            store_pk = str(store.pk) if getattr(store, "pk", None) else None
            store_owner_id = str(store.owner_id) if getattr(store, "owner_id", None) else None
            user_pk = str(user.pk) if getattr(user, "pk", None) else None

            return (
                (user_store_id is not None and user_store_id == store_pk)
                or (store_owner_id is not None and store_owner_id == user_pk)
                or StoreEmployee.objects.filter(store=store, user=user).exists()
            )


# Backward compatibility alias
TenantMiddleware = TenantSecurityMiddleware

