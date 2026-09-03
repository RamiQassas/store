from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
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


from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
import subprocess

def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /control/\n", content_type="text/plain")

@csrf_exempt
def deploy_webhook(request, secret_token):
    if secret_token != "raqamiyat_deploy_secret_2026":
        return HttpResponseForbidden("Invalid secret token")
    try:
        subprocess.Popen(["/bin/sh", "-c", "cd /app && git pull origin master || true"])
        return JsonResponse({"status": "success", "message": "Deployment triggered successfully!"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def version_view(request):
    import subprocess
    commit_sha = "unknown"
    commit_msg = "unknown"
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            commit_sha = res.stdout.strip()
        res_msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True, timeout=5)
        if res_msg.returncode == 0:
            commit_msg = res_msg.stdout.strip()
    except Exception:
        pass

    diag = {}
    try:
        from apps.providers.models import ProviderProfile, ProviderProduct
        from apps.catalog.models import ProductVariant, Product
        from apps.site.models import APIIntegration
        
        diag["profiles"] = [
            {
                "id": str(p.id),
                "name": p.provider_name,
                "base_url": p.base_url,
                "prod_count_total": ProviderProduct.objects.filter(profile=p).count(),
                "prod_count_active": ProviderProduct.objects.filter(profile=p, is_active=True).count(),
            }
            for p in ProviderProfile.all_objects.all()
        ]
        diag["integrations"] = [
            {"id": str(i.id), "name": i.name, "provider": i.provider, "base_url": i.base_url}
            for i in APIIntegration.objects.all()
        ]
        diag["tafa3ol_products_count"] = Product.objects.filter(api_provider="tafa3olcard").count()
        diag["tafa3ol_variants_count"] = ProductVariant.objects.filter(product__api_provider="tafa3olcard").count()
    except Exception as e:
        diag["error"] = str(e)

    return JsonResponse({
        "status": "online",
        "commit_sha": commit_sha,
        "commit_short_sha": commit_sha[:7],
        "commit_message": commit_msg,
        "diag": diag,
    })


from apps.common.auto_deploy import github_auto_deploy_view

urlpatterns = [
    path("robots.txt", robots_txt),
    path("api/version/", version_view, name="version_view"),
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
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
