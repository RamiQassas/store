from rest_framework import decorators, response, viewsets, status
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, PushSubscription
from apps.notifications.serializers import NotificationSerializer

User = get_user_model()


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    filterset_fields = ("is_read", "channel")

    def get_queryset(self):
        queryset = Notification.objects.select_related("user")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        if self.request.user.is_staff and self.request.data.get("user"):
            user = User.objects.get(id=self.request.data["user"])
        serializer.save(user=user)

    @decorators.action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        data = request.data
        endpoint = data.get("endpoint")
        if not endpoint:
            return response.Response({"error": "Endpoint required"}, status=status.HTTP_400_BAD_REQUEST)
            
        PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                "p256dh": data.get("p256dh", ""),
                "auth": data.get("auth", ""),
                "browser": data.get("browser", "")
            }
        )
        return response.Response({"status": "subscribed"})

    @decorators.action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read", "updated_at"])
        return response.Response(self.get_serializer(notification).data)
