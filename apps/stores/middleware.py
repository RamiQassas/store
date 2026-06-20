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
                
        print(f"[TenantMiddleware] Host: {host}, main_domain: {main_domain}, main_domains: {main_domains}")
        
        # 3. Check if host matches main domain or subdomain
        request.store = None
        is_subdomain = False
        subdomain = ""
        
        # Check against each configured main domain
        for m_domain in main_domains:
            # Clean www. from matched base domain if it exists
            cleaned_m_domain = m_domain[4:] if m_domain.startswith("www.") else m_domain
            if host.endswith("." + cleaned_m_domain) and host != cleaned_m_domain:
                subdomain = host[:-(len(cleaned_m_domain) + 1)]
                is_subdomain = True
                if subdomain == "www":
                    is_subdomain = False
                break

        if not is_subdomain and main_domain in ["localhost", "127.0.0.1", "testserver"]:
            # For local testing (including Django test client), parse first part as subdomain
            parts = host.split('.')
            if len(parts) > 1 and parts[-1] in ["localhost", "127", "testserver"]:
                subdomain = parts[0]
                is_subdomain = True

        print(f"[TenantMiddleware] is_subdomain: {is_subdomain}, subdomain: {subdomain}")

        from django.http import Http404, HttpResponseForbidden

        if is_subdomain:
            try:
                # Bypass tenant filter during store lookup
                from apps.common.tenant_utils import bypass_tenant_filter
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
                
                # Required logging
                print(request.get_host())
                print(subdomain)
                print(store)

                if not store.is_active:
                    print(f"[TenantMiddleware] Store '{store}' is inactive. Returning Forbidden.")
                    return HttpResponseForbidden("<h1>المتجر موقوف مؤقتاً</h1><p>هذا المتجر تم إيقافه مؤقتاً من قبل إدارة المنصة.</p>")
                request.store = store
            except Store.DoesNotExist:
                # Required logging for failed lookup
                print(request.get_host())
                print(subdomain)
                print(None)
                raise Http404("المتجر المطلوب غير موجود.")
            except Exception as e:
                print(f"[TenantMiddleware] Error during subdomain lookup: {str(e)}")
        else:
            # Check for custom domains
            is_main_domain_or_local = (host in main_domains) or (host in ["localhost", "127.0.0.1", "testserver"]) or any(host.endswith("." + d) for d in main_domains)
            if not is_main_domain_or_local:
                try:
                    from apps.common.tenant_utils import bypass_tenant_filter
                    with bypass_tenant_filter():
                        store = Store.objects.filter(custom_domain=host).first()
                    print(f"[TenantMiddleware] Resolved store for custom domain '{host}': {store}")
                    if store:
                        if not store.is_active:
                            print(f"[TenantMiddleware] Store '{store}' is inactive. Returning Forbidden.")
                            return HttpResponseForbidden("<h1>المتجر موقوف مؤقتاً</h1><p>هذا المتجر تم إيقافه مؤقتاً من قبل إدارة المنصة.</p>")
                        request.store = store
                    else:
                        raise Http404("هذا النطاق غير مرتبط بأي متجر على المنصة.")
                except Http404:
                    raise
                except Exception as e:
                    print(f"[TenantMiddleware] Error during custom domain lookup: {str(e)}")

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
