import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.catalog.models import ProductVariant
from apps.common.models import TimeStampedModel
from apps.common.tenant_utils import TenantManager


class Coupon(TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "نسبة مئوية (%)"
        FIXED_AMOUNT = "fixed_amount", "مبلغ ثابت (USD)"

    code = models.CharField(max_length=40, verbose_name="الكود")
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.PERCENTAGE, verbose_name="نوع الخصم")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة الخصم (%)")
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة الخصم (USD)")
    max_uses = models.PositiveIntegerField(default=0, verbose_name="أقصى عدد استخدام لجميع المستخدمين (0 = غير محدود)")
    max_uses_per_user = models.PositiveIntegerField(default=1, verbose_name="أقصى عدد استخدام لكل مستخدم")
    used_count = models.PositiveIntegerField(default=0, verbose_name="إجمالي عدد المرات التي تم استخدامه")
    min_order_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="الحد الأدنى للطلب (USD)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coupons",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    is_verified_only = models.BooleanField(default=True, verbose_name="للحسابات الموثقة فقط")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    valid_for_users_before = models.DateTimeField(null=True, blank=True, verbose_name="صالح للحسابات المسجلة قبل تاريخ")
    valid_for_users_after = models.DateTimeField(null=True, blank=True, verbose_name="صالح للحسابات المسجلة بعد تاريخ")
    
    limit_to_products = models.ManyToManyField("catalog.Product", blank=True, verbose_name="محدد لمنتجات معينة")
    apply_to_all_products = models.BooleanField(default=True, verbose_name="يعمل على جميع المنتجات")
    
    # New Restrictions
    limit_to_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, verbose_name="محدد لعملاء معينين")
    limit_to_tiers = models.JSONField(default=list, blank=True, verbose_name="محدد لفئات معينة (Tiers)")
    limit_to_area = models.CharField(max_length=255, blank=True, verbose_name="محدد لمنطقة معينة (كلمة دلالية)")
    
    class AreaType(models.TextChoices):
        RESIDENCE = "residence", "مكان الإقامة الحالي"
        BIRTH = "birth", "مكان الولادة"
        BOTH = "both", "كلاهما"
        
    allow_area_type = models.CharField(max_length=20, choices=AreaType.choices, default=AreaType.RESIDENCE, verbose_name="نوع المطابقة الجغرافية")
    limit_to_place_of_birth = models.CharField(max_length=255, blank=True, verbose_name="محدد لمحل الولادة (كلمة دلالية)")

    # New Logic (Task 3)
    class MatchMode(models.TextChoices):
        ALL = "all", "يجب تحقق جميع الشروط (AND)"
        ANY = "any", "يكفي تحقق أي شرط واحد (OR)"
        
    match_mode = models.CharField(max_length=10, choices=MatchMode.choices, default=MatchMode.ALL, verbose_name="طريقة المطابقة")

    # IP-based Geographic matching (Task 2)
    limit_to_ip_countries = models.JSONField(default=list, blank=True, verbose_name="محدد لدول معينة (IP-based)")
    limit_to_ip_cities = models.JSONField(default=list, blank=True, verbose_name="محدد لمدن/مناطق معينة (IP-based)")

    class Meta:
        verbose_name = "كوبون"
        verbose_name_plural = "الكوبونات"
        unique_together = ("store", "code")

    def __str__(self):
        return self.code


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing", "قيد المعالجة"
        COMPLETED = "completed", "مكتمل"
        REFUNDED = "refunded", "مسترد"
        CANCELLED = "cancelled", "ملغى"
        DISPUTED = "disputed", "متنازع عليه"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT, verbose_name="العميل")
    store = models.ForeignKey(
        "stores.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="المتجر"
    )
    objects = TenantManager()
    all_objects = models.Manager()
    number = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="رقم الطلب")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING, verbose_name="الحالة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المبلغ")
    original_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="المبلغ الأصلي قبل التعديل")
    price_adjustment_reason = models.TextField(blank=True, verbose_name="سبب تعديل السعر")
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="الكوبون")
    fulfillment_data = models.JSONField(default=dict, blank=True, verbose_name="بيانات التنفيذ")
    admin_note = models.TextField(blank=True, verbose_name="ملاحظات المدير")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    is_delivery_read = models.BooleanField(default=False, verbose_name="تمت رؤية المنتج الرقمي")

    class Meta:
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_status = Order.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            except Exception:
                pass

        if not self.number:
            self.number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

        if self.status == Order.Status.COMPLETED and old_status != Order.Status.COMPLETED:
            self.generate_recharge_cards()

    def generate_recharge_cards(self):
        from apps.wallets.models import RechargeCard
        from apps.common.models import Currency
        import secrets

        generated_codes = []
        for item in self.items.all():
            variant = item.variant
            if getattr(variant, "is_recharge_card", False):
                for _ in range(item.quantity):
                    code = f"RC-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
                    amount = variant.recharge_amount
                    if amount <= 0:
                        amount = variant.price
                    currency = variant.recharge_currency
                    if not currency:
                        currency = Currency.objects.filter(code="USD").first() or Currency.objects.filter(is_default=True).first()

                    RechargeCard.objects.create(
                        code=code,
                        amount=amount,
                        currency=currency,
                        order=self,
                        status=RechargeCard.Status.ACTIVE,
                        store=self.store
                    )
                    generated_codes.append(code)

        if generated_codes:
            ff_data = dict(self.fulfillment_data or {})
            existing_codes = ff_data.get("أكواد الشحن", "")
            all_codes = [c.strip() for c in existing_codes.split("|") if c.strip()] if existing_codes else []
            all_codes.extend(generated_codes)
            ff_data["أكواد الشحن"] = " | ".join(all_codes)
            Order.objects.filter(pk=self.pk).update(fulfillment_data=ff_data)

    def formatted_metadata(self):
        """Returns a list of dicts with 'label' and 'value' for metadata."""
        if not self.metadata:
            return []
            
        results = []
        first_item = self.items.first()
        schema = {}
        if first_item and first_item.variant and first_item.variant.product:
            schema = first_item.variant.product.form_schema
            
        fields = schema.get("fields", []) if isinstance(schema, dict) else []
        
        # Create a mapping of field key to label
        label_map = {}
        for f in fields:
            lbl = f.get("label", "")
            fid = f.get("name") or f.get("id") or f.get("key") or lbl
            if fid:
                label_map[fid] = lbl
        
        for key, val in self.metadata.items():
            label = label_map.get(key, key)
            results.append({"label": label, "value": val})
                
        return results

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["number"]),
        ]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE, verbose_name="الطلب")
    variant = models.ForeignKey(ProductVariant, related_name="order_items", on_delete=models.PROTECT, verbose_name="الباقة")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="سعر الوحدة")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="تكلفة الوحدة")
    total_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="السعر الإجمالي")

    class Meta:
        verbose_name = "بند طلب"
        verbose_name_plural = "بنود الطلبات"

    def __str__(self):
        return f"{self.order.number} - {self.variant}"


class OrderLog(TimeStampedModel):
    order = models.ForeignKey(Order, related_name="logs", on_delete=models.CASCADE, verbose_name="الطلب")
    status = models.CharField(max_length=20, choices=Order.Status.choices, verbose_name="الحالة")
    note = models.TextField(blank=True, verbose_name="ملاحظة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="من قبل")

    class Meta:
        verbose_name = "سجل طلب"
        verbose_name_plural = "سجلات الطلبات"
        ordering = ["created_at"]


class Invoice(TimeStampedModel):
    order = models.OneToOneField(Order, related_name="invoice", on_delete=models.CASCADE, verbose_name="الطلب")
    invoice_number = models.CharField(max_length=40, unique=True, verbose_name="رقم الفاتورة")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="المبلغ الإجمالي")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإصدار")

    class Meta:
        verbose_name = "فاتورة"
        verbose_name_plural = "الفواتير"
