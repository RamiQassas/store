from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import SecurityEvent, UserSession
from apps.accounts.serializers import LoginSerializer, RegisterSerializer, UserSerializer, UserSessionSerializer


def request_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def token_payload(user, request):
    refresh = RefreshToken.for_user(user)
    UserSession.objects.create(
        user=user,
        refresh_jti=refresh["jti"],
        ip_address=request_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        last_seen_at=timezone.now(),
    )
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        SecurityEvent.objects.create(
            user=user,
            event_type=SecurityEvent.EventType.LOGIN,
            ip_address=request_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            metadata={"source": "register"},
        )
        return Response({"user": UserSerializer(user).data, "tokens": token_payload(user, request)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        SecurityEvent.objects.create(
            user=user,
            event_type=SecurityEvent.EventType.LOGIN,
            ip_address=request_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"user": UserSerializer(user).data, "tokens": token_payload(user, request)})


class UserSessionViewSet(mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user, is_active=True)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
