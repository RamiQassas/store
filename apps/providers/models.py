from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.common.models import TimeStampedModel
from apps.common.tenant_utils import TenantManager

class ProviderProfile(TimeStampedModel):
    """Stores authentication and configuration for a provider."""
    store = models.ForeignKey(
        "stores.Store", on_delete=models.CASCADE, null=True, blank=True,
        related_name="provider_profiles", verbose_name="المتجر"
    )
    provider_name = models.CharField(max_length=50, verbose_name="اسم المزود")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    base_url = models.URLField(max_length=255, blank=True, null=True, verbose_name="الرابط الأساسي")
    api_token = models.CharField(max_length=255, blank=True, null=True, verbose_name="مفتاح الـ API")
    balance = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.00'), verbose_name="الرصيد")
    currency = models.CharField(max_length=10, default="USD", verbose_name="العملة")
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ آخر مزامنة")

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "ملف تعريف المزود"
        verbose_name_plural = "ملفات تعريف المزودين"

    def __str__(self):
        return f"{self.provider_name} ({self.store.name if self.store else 'عام'})"


class ProviderCategory(TimeStampedModel):
    """Mirrors the category tree returned by the provider."""
    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="categories")
    remote_id = models.CharField(max_length=100, verbose_name="معرف التصنيف في المزود")
    name = models.CharField(max_length=255, verbose_name="اسم التصنيف")
    parent_remote_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="معرف الأب في المزود")
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    class Meta:
        unique_together = ('profile', 'remote_id')

    def __str__(self):
        return self.name


class ProviderProduct(TimeStampedModel):
    """Mirrors a product returned by the provider."""
    PRODUCT_TYPES = (
        ("package", "Package"),
        ("amount", "Amount"),
        ("fixed_quantities", "Fixed Quantities"),
        ("category_only", "Category Only"),
    )

    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(ProviderCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    remote_id = models.CharField(max_length=100, verbose_name="معرف المنتج في المزود")
    name = models.CharField(max_length=255, verbose_name="اسم المنتج")
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPES, default="package", verbose_name="نوع المنتج")
    is_active = models.BooleanField(default=True, verbose_name="نشط في المزود")
    
    # Pricing
    cost_price = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.00'), verbose_name="سعر التكلفة من المزود")
    
    # Store Customizations (These survive syncs)
    local_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="الاسم المخصص")
    local_description = models.TextField(null=True, blank=True, verbose_name="الوصف المخصص")
    local_is_active = models.BooleanField(default=True, verbose_name="ظاهر في المتجر")
    local_image = models.ImageField(upload_to="provider_products/", null=True, blank=True, verbose_name="الصورة المخصصة")
    local_sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    local_seo_title = models.CharField(max_length=255, null=True, blank=True)
    local_seo_keywords = models.CharField(max_length=255, null=True, blank=True)

    # Quantity configurations
    qty_min = models.BigIntegerField(null=True, blank=True)
    qty_max = models.BigIntegerField(null=True, blank=True)
    qty_list = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('profile', 'remote_id')

    def __str__(self):
        return self.local_name or self.name


class ProviderProductParameter(TimeStampedModel):
    """Parameters required by the provider for a product (e.g. playerId, serverId)"""
    product = models.ForeignKey(ProviderProduct, on_delete=models.CASCADE, related_name="parameters")
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=100)
    required = models.BooleanField(default=True)
    parameter_type = models.CharField(max_length=50, default="text")

    def __str__(self):
        return self.name


class ProviderPrice(TimeStampedModel):
    """Pricing configuration and history for a ProviderProduct."""
    product = models.OneToOneField(ProviderProduct, on_delete=models.CASCADE, related_name="pricing")
    margin_type = models.CharField(
        max_length=20, 
        choices=(("fixed", "مبلغ ثابت"), ("percentage", "نسبة مئوية"), ("manual", "سعر يدوي")),
        default="percentage"
    )
    margin_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    manual_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    round_to_nearest = models.BooleanField(default=False)
    
    @property
    def final_price(self):
        if self.margin_type == "manual" and self.manual_price is not None:
            return self.manual_price
        
        cost = self.product.cost_price
        if self.margin_type == "fixed":
            return cost + self.margin_value
        elif self.margin_type == "percentage":
            return cost + (cost * (self.margin_value / Decimal('100.0')))
        return cost


class ProviderPriceHistory(TimeStampedModel):
    """History of price changes for audit purposes."""
    product = models.ForeignKey(ProviderProduct, on_delete=models.CASCADE, related_name="price_history")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    old_cost = models.DecimalField(max_digits=14, decimal_places=4)
    new_cost = models.DecimalField(max_digits=14, decimal_places=4)
    old_final_price = models.DecimalField(max_digits=14, decimal_places=2)
    new_final_price = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)


class ProviderOrder(TimeStampedModel):
    """Tracks an order sent to a provider."""
    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="orders")
    local_order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="provider_orders")
    product = models.ForeignKey(ProviderProduct, on_delete=models.CASCADE, related_name="provider_orders")
    
    # Local identifier sent to provider
    uuid = models.UUIDField(unique=True)
    
    # Provider's identifier returned after successful submission
    remote_order_id = models.CharField(max_length=100, null=True, blank=True)
    
    status = models.CharField(max_length=50, default="pending")
    cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    parameters_sent = models.JSONField(default=dict)


class ProviderOrderStatus(TimeStampedModel):
    """Status history of a ProviderOrder."""
    provider_order = models.ForeignKey(ProviderOrder, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=50)
    raw_response = models.JSONField(default=dict, blank=True)


class ProviderSyncLog(TimeStampedModel):
    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="sync_logs")
    status = models.CharField(max_length=20) # 'success', 'failed', 'running'
    products_created = models.IntegerField(default=0)
    products_updated = models.IntegerField(default=0)
    products_disabled = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)


class ProviderRequestLog(TimeStampedModel):
    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="request_logs")
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    payload = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)


class ProviderResponseLog(TimeStampedModel):
    request_log = models.OneToOneField(ProviderRequestLog, on_delete=models.CASCADE, related_name="response")
    status_code = models.IntegerField(null=True, blank=True)
    body = models.TextField(blank=True)
    is_success = models.BooleanField(default=False)


class ProviderErrorLog(TimeStampedModel):
    profile = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="error_logs")
    error_code = models.CharField(max_length=50, null=True, blank=True)
    message = models.TextField()
    traceback = models.TextField(blank=True)
    related_request = models.ForeignKey(ProviderRequestLog, on_delete=models.SET_NULL, null=True, blank=True)


class ProviderMapping(TimeStampedModel):
    """Maps local store catalog Category/Product to ProviderCategory/ProviderProduct"""
    local_product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="provider_mappings", null=True, blank=True)
    local_variant = models.OneToOneField("catalog.ProductVariant", on_delete=models.CASCADE, related_name="provider_mapping", null=True, blank=True)
    provider_product = models.ForeignKey(ProviderProduct, on_delete=models.CASCADE, related_name="mappings")
