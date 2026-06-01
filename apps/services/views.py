from rest_framework import viewsets

from apps.common.permissions import ReadOnlyOrAdmin
from apps.services.models import Service
from apps.services.serializers import ServiceSerializer


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [ReadOnlyOrAdmin]
    filterset_fields = ("service_type", "is_active")
    search_fields = ("name", "slug", "description")

    def get_queryset(self):
        queryset = Service.objects.prefetch_related("fields")
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset
