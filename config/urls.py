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
        cmd = "cd /app && git pull origin master && python manage.py remap_alkasr_catalog || true"
        subprocess.Popen(["/bin/sh", "-c", cmd])
        return JsonResponse({"status": "success", "message": "Deployment triggered successfully with catalog remap!"})
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

    diag = None
    if request.GET.get("restart") == "1":
        import os, threading, time
        def _die():
            time.sleep(0.5)
            os._exit(0)
        threading.Thread(target=_die, daemon=True).start()
        return JsonResponse({"status": "restarting"})
    if request.GET.get("remap") == "1":
        try:
            import threading
            from django.core.management import call_command
            def _bg_remap():
                from django.db import connection
                connection.close()
                try:
                    call_command("remap_alkasr_catalog")
                except Exception as err:
                    import logging
                    logging.getLogger("auto_deploy").exception(f"BG remap error: {err}")
            threading.Thread(target=_bg_remap, daemon=True).start()
            diag = {"status": "remap_alkasr_catalog_started_in_background"}
        except Exception as e:
            diag = {"error": str(e)}
    if request.GET.get("sync_tafa3ol") == "1":
        try:
            import threading
            from apps.providers.models import ProviderProfile
            from services.provider.tafa3olcard import Tafa3olCardProviderService
            
            p = ProviderProfile.all_objects.filter(base_url__icontains="tafa3ol").first()
            if p:
                def _bg_sync():
                    from django.db import connection
                    connection.close()
                    try:
                        svc = Tafa3olCardProviderService(api_token=p.api_token, base_url=p.base_url, profile_model=p)
                        svc.sync_catalog()
                    except Exception as err:
                        import logging
                        logging.getLogger("auto_deploy").exception(f"BG sync error: {err}")

                threading.Thread(target=_bg_sync, daemon=True).start()
                diag = {"status": "sync_started_in_background"}
        except Exception as e:
            import traceback
            diag = {"error": str(e), "traceback": traceback.format_exc()}
    elif request.GET.get("diag") == "tafa3ol":
        try:
            from apps.providers.models import ProviderProfile, ProviderProduct
            from apps.catalog.models import Product, ProductVariant
            from apps.orders.models import OrderLog
            from services.provider.tafa3olcard import Tafa3olCardProviderService
            
            p = ProviderProfile.all_objects.filter(base_url__icontains="tafa3ol").first()
            svc = Tafa3olCardProviderService(api_token=p.api_token, base_url=p.base_url, profile_model=p) if p else None

            dot_prods_count = Product.objects.filter(api_provider="tafa3olcard", name__regex=r'^[\.\s\-_=~*#]+$').count()
            prods_count = Product.objects.filter(api_provider="tafa3olcard").count()
            variants_count = ProductVariant.objects.filter(product__api_provider="tafa3olcard").count()
            
            game_samples = list(ProductVariant.objects.filter(
                product__api_provider="tafa3olcard"
            ).exclude(cost=0).values("product__name", "name", "price", "cost")[:8])

            zero_samples = list(ProductVariant.objects.filter(
                product__api_provider="tafa3olcard",
                cost=0
            ).values("product__name", "name", "price", "cost")[:5])

            categories = list(Product.objects.filter(api_provider="tafa3olcard").values_list("category__name", flat=True).distinct())

            diag = {
                "prods_count": prods_count,
                "variants_count": variants_count,
                "dot_prods_count": dot_prods_count,
                "categories": categories,
                "priced_samples": game_samples,
                "zero_cost_samples": zero_samples,
            }
        except Exception as e:
            import traceback
            diag = {"error": str(e), "traceback": traceback.format_exc()}
    elif request.GET.get("diag") == "stores":
        try:
            from apps.stores.models import Store
            from apps.catalog.models import Category, Product
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                diag = {
                    "stores": [
                        {
                            "id": str(s.id),
                            "name": s.name,
                            "subdomain": s.subdomain,
                            "custom_domain": s.custom_domain,
                            "is_active": s.is_active,
                            "cats_count": Category.all_objects.filter(store=s).count(),
                            "prods_count": Product.all_objects.filter(store=s).count(),
                        }
                        for s in Store.objects.all()
                    ],
                    "main_cats": Category.all_objects.filter(store__isnull=True).count(),
                    "main_prods": Product.all_objects.filter(store__isnull=True).count(),
                }
        except Exception as e:
            import traceback
            diag = {"error": str(e), "traceback": traceback.format_exc()}
    elif request.GET.get("diag") == "users":
        try:
            from apps.accounts.models import User
            from apps.stores.models import Store, StoreEmployee
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                u_list = list(User.all_objects.filter(email__icontains="ramikasas").values(
                    "id", "email", "role", "store_id", "is_staff", "is_superuser", "is_active", "status", "last_session_key", "email_verified"
                ))
                pubg_store = Store.unfiltered.filter(subdomain="pubg").first()
                membership_info = []
                for u_dict in u_list:
                    u = User.all_objects.get(id=u_dict["id"])
                    membership_info.append({
                        "user_id": u.id,
                        "store_id": str(u.store_id),
                        "pubg_store_id": str(pubg_store.id) if pubg_store else None,
                        "pubg_owner_id": str(pubg_store.owner_id) if pubg_store else None,
                        "user_store_equals": (u.store_id == pubg_store.id) if pubg_store else None,
                        "owner_equals": (pubg_store.owner_id == u.pk) if pubg_store else None,
                        "employee_exists": StoreEmployee.objects.filter(store=pubg_store, user=u).exists() if pubg_store else None,
                    })
                diag = {"users": u_list, "memberships": membership_info}
        except Exception as e:
            import traceback
            diag = {"error": str(e), "traceback": traceback.format_exc()}

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
