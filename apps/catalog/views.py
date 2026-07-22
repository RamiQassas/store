from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.catalog.models import Category, Product
from apps.catalog.serializers import CategorySerializer, ProductSerializer
from apps.common.permissions import ReadOnlyOrAdmin


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [ReadOnlyOrAdmin]
    search_fields = ("name", "slug")
    ordering_fields = ("sort_order", "name", "created_at")

    def get_queryset(self):
        queryset = Category.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [ReadOnlyOrAdmin]
    filterset_fields = ("category", "delivery_type", "is_featured")
    search_fields = ("name", "slug", "description")
    ordering_fields = ("sort_order", "name", "created_at")

    def get_queryset(self):
        queryset = Product.objects.select_related("category", "category__parent").prefetch_related(
            "variants", "variants__tier_prices"
        )
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True, variants__is_active=True).distinct()
        return queryset
