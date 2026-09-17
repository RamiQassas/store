from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import LoginView, RegisterView, UserSessionViewSet
from apps.catalog.views import CategoryViewSet, ProductViewSet
from apps.notifications.views import NotificationViewSet
from apps.orders.views import CouponViewSet, OrderViewSet
from apps.payments.views import DepositRequestViewSet, PaymentMethodViewSet, WithdrawalRequestViewSet
from apps.services.views import ServiceViewSet
from apps.wallets.views import WalletViewSet
from apps.common.views import protected_media

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("wallets", WalletViewSet, basename="wallet")
router.register("payment-methods", PaymentMethodViewSet, basename="payment-method")
router.register("deposits", DepositRequestViewSet, basename="deposit")
router.register("withdrawals", WithdrawalRequestViewSet, basename="withdrawal")
router.register("orders", OrderViewSet, basename="order")
router.register("coupons", CouponViewSet, basename="coupon")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("services", ServiceViewSet, basename="service")
router.register("sessions", UserSessionViewSet, basename="session")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "digital-marketplace"})


import hmac
import threading

from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
import subprocess

from apps.site.seo_views import sitemap_xml_view, custom_404_view, custom_500_view

def robots_txt(request):
    host = request.get_host()
    scheme = "https" if (request.is_secure() or request.headers.get("X-Forwarded-Proto") == "https") else "http"
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /catalog/\n"
        "Allow: /stores/\n"
        "Allow: /privacy-policy/\n"
        "Allow: /terms-of-service/\n"
        "Allow: /refund-policy/\n"
        "Allow: /contact/\n"
        "Allow: /media/\n"
        "Allow: /static/\n"
        "Disallow: /control/\n"
        "Disallow: /dashboard/\n"
        "Disallow: /api/\n"
        "Disallow: /payments/\n"
        "Disallow: /auth/\n"
        "Disallow: /ajax/\n"
        f"\nSitemap: {scheme}://{host}/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain")

@require_POST
@csrf_exempt
def deploy_webhook(request, secret_token):
    """Legacy deployment hook, disabled unless explicitly configured."""
    token = settings.LEGACY_DEPLOY_WEBHOOK_TOKEN
    if not settings.AUTO_DEPLOY_ENABLED or not token:
        return HttpResponseNotFound()
    if not hmac.compare_digest(str(secret_token), token):
        return HttpResponseForbidden("Invalid secret token")

    def run_deploy():
        try:
            subprocess.run(["git", "pull", "origin", "master"], cwd="/app", check=True, timeout=60)
            subprocess.run(["python", "manage.py", "remap_alkasr_catalog"], cwd="/app", check=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            # The operation is intentionally not reflected to an unauthenticated caller.
            return

    threading.Thread(target=run_deploy, daemon=True).start()
    return JsonResponse({"status": "accepted"}, status=202)


@require_GET
def version_view(request):
    """Public liveness endpoint with no operational controls or sensitive data."""
    return JsonResponse({"status": "online"})


@require_GET
def debug_provider_products(request):
    from apps.providers.models import ProviderProduct, ProviderProfile
    from apps.catalog.models import ProductVariant
    profile = ProviderProfile.all_objects.filter(is_active=True).first()
    token = (profile.api_token[:6] + "...") if (profile and profile.api_token) else None
    
    prods = []
    for p in ProviderProduct.objects.all():
        # find mapped variant
        mapping = getattr(p, 'mapping', None)
        v = mapping.local_variant if mapping else None
        prods.append({
            "id": p.id,
            "remote_id": p.remote_id,
            "name": p.name,
            "local_name": p.local_name,
            "cost_price": str(p.cost_price),
            "product_type": p.product_type,
            "qty_min": p.qty_min,
            "qty_max": p.qty_max,
            "qty_list": p.qty_list,
            "category": p.category.name if p.category else None,
            "parent_category": p.category.parent.name if p.category and p.category.parent else None,
            "variant_price": str(v.price) if v else None,
            "variant_name": v.name if v else None,
            "variant_qty_type": (v.metadata or {}).get("qty_type") if v else None,
            "variant_meta": v.metadata if v else None,
        })
    return JsonResponse({"count": len(prods), "token_prefix": token, "products": prods})



@require_GET
def alkasr_raw_products(request):
    from apps.providers.models import ProviderProfile
    from services.provider.alkasr.client import AlkasrClient
    profile = ProviderProfile.all_objects.filter(is_active=True).first()
    if not profile:
        return JsonResponse({"error": "No profile"})
    client = AlkasrClient(api_token=profile.api_token, base_url=profile.base_url, profile=profile)
    raw = client.get_products()
    raw_list = raw if isinstance(raw, list) else raw.get("data", [])
    
    # filter if query param 'ids' passed
    ids_param = request.GET.get("ids")
    if ids_param:
        target_ids = [x.strip() for x in ids_param.split(",") if x.strip()]
        filtered = [item for item in raw_list if str(item.get("id")) in target_ids or str(item.get("name")).lower() in [t.lower() for t in target_ids]]
        return JsonResponse({"count": len(filtered), "items": filtered})
    
    return JsonResponse({"total": len(raw_list), "sample": raw_list[:20]})


from apps.common.auto_deploy import github_auto_deploy_view

urlpatterns = [
    path("robots.txt", robots_txt),
    path("sitemap.xml", sitemap_xml_view, name="sitemap_xml"),
    path("api/version/", version_view, name="version_view"),
    path("api/debug-products/", debug_provider_products, name="debug_provider_products"),
    path("api/alkasr-raw/", alkasr_raw_products, name="alkasr_raw_products"),
    path("api/deploy-webhook/<str:secret_token>/", deploy_webhook, name="deploy_webhook"),
    path("api/github-auto-deploy/", github_auto_deploy_view, name="github_auto_deploy"),
    path("", include("apps.site.urls")),

    path("support/", include("apps.support.urls")),
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
    path('accounts/', include('allauth.urls')),
    path("media/<path:path>", protected_media, name="protected_media"),
]

handler404 = "apps.site.seo_views.custom_404_view"
handler500 = "apps.site.seo_views.custom_500_view"
