from django.conf import settings
from apps.stores.models import Store
from urllib.parse import urlparse

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Get host name from request
        host = request.get_host().split(':')[0].lower()
        
        # 2. Determine main domain
        site_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
        main_domain = urlparse(site_url).hostname or "raqamiyatapp.com"
        main_domain = main_domain.lower()
        
        # 3. Check if host matches main domain or subdomain
        request.store = None
        is_subdomain = False
        subdomain = ""
        
        if host.endswith("." + main_domain) and host != main_domain:
            subdomain = host[:-(len(main_domain) + 1)]
            is_subdomain = True
            if subdomain == "www":
                is_subdomain = False
        elif main_domain in ["localhost", "127.0.0.1", "testserver"]:
            # For local testing (including Django test client), parse first part as subdomain
            parts = host.split('.')
            if len(parts) > 1 and parts[-1] in ["localhost", "127", "testserver"]:
                subdomain = parts[0]
                is_subdomain = True

        if is_subdomain:
            try:
                # Bypass tenant filter during store lookup
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    store = Store.objects.filter(slug=subdomain, is_active=True).first()
                if store:
                    request.store = store
            except Exception:
                pass
        else:
            if host != main_domain and host not in ["localhost", "127.0.0.1", "testserver"]:
                try:
                    from apps.common.tenant_utils import bypass_tenant_filter
                    with bypass_tenant_filter():
                        store = Store.objects.filter(custom_domain=host, is_active=True).first()
                    if store:
                        request.store = store
                except Exception:
                    pass

        # 4. Handle tenant routing and context binding
        if request.store:
            request.urlconf = 'apps.stores.urls'
            from apps.common.tenant_utils import set_current_store
            token = set_current_store(request.store)
            request._tenant_token = token
        else:
            # Main site: check if admin or control panel request by super admin/staff, then bypass
            # request.user is set by AuthenticationMiddleware
            if hasattr(request, 'user') and request.user.is_authenticated and (request.user.role == 'super_admin' or request.user.is_superuser or request.user.is_staff):
                if request.path.startswith('/admin/') or request.path.startswith('/control/'):
                    from apps.common.tenant_utils import _bypass_tenant_filter
                    token = _bypass_tenant_filter.set(True)
                    request._bypass_token = token

        try:
            response = self.get_response(request)
        finally:
            # Clean up context variables to prevent thread leaking
            if hasattr(request, '_tenant_token'):
                from apps.common.tenant_utils import reset_current_store
                reset_current_store(request._tenant_token)
            if hasattr(request, '_bypass_token'):
                from apps.common.tenant_utils import _bypass_tenant_filter
                _bypass_tenant_filter.reset(request._bypass_token)

        return response
