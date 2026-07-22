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


from django.http import HttpResponse

def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /control/\n", content_type="text/plain")

urlpatterns = [
    path("robots.txt", robots_txt),
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
