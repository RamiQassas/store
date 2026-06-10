from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid
from decimal import Decimal

from apps.accounts.managers import UserManager
from apps.common.models import TimeStampedModel
from apps.common.countries import COUNTRIES


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "مدير عام"
        ADMIN = "admin", "مدير"
        MODERATOR = "moderator", "مشرف"
        FINANCE = "finance", "مالية"
        SUPPORT = "support", "دعم"
        EMPLOYEE = "employee", "موظف"
        VERIFIED_MERCHANT = "verified_merchant", "تاجر معتمد"
        CUSTOMER = "customer", "عميل"

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "موقوف مؤقتاً"
        FROZEN = "frozen", "مجمد"
        RESTRICTED = "restricted", "مقيد"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        BANNED = "banned", "محظور نهائياً"

    class Tier(models.TextChoices):
        CUSTOMER = "customer", "عميل"
        DEALER = "dealer", "تاجر معتمد"
        VIP = "vip", "VIP"

    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.CUSTOMER)
    
    # Tiers
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.CUSTOMER, verbose_name="الفئة")
    
    # Account Status & Moderation
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE, verbose_name="حالة الحساب")
    restriction_withdrawals = models.BooleanField(default=False, verbose_name="تقييد السحب")
    restriction_deposits = models.BooleanField(default=False, verbose_name="تقييد الإيداع")
    restriction_purchases = models.BooleanField(default=False, verbose_name="تقييد الشراء")
    
    suspension_reason = models.TextField(blank=True, verbose_name="سبب الإيقاف (للمستخدم)")
    admin_notes = models.TextField(blank=True, verbose_name="ملاحظات المشرف (داخلية)")
    suspension_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ انتهاء الإيقاف")
    is_permanently_suspended = models.BooleanField(default=False, verbose_name="إيقاف نهائي")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    public_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    preferred_currency = models.ForeignKey("common.Currency", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="العملة المفضلة")
    preferred_language = models.CharField(max_length=10, default="ar", verbose_name="اللغة المفضلة")
    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)

    # KYC & Limits
    is_kyc_verified = models.BooleanField(default=False, verbose_name="موثق الهوية")
    has_custom_limits = models.BooleanField(default=False, verbose_name="له حدود مخصصة")
    daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("100.00"), verbose_name="حد الإيداع اليومي")
    daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("100.00"), verbose_name="حد السحب اليومي")
    
    # Per-payment method custom limits for this user
    # Format: {"method_id": {"deposit": 500, "withdraw": 500}}
    custom_payment_limits = models.JSONField(default=dict, blank=True, verbose_name="حدود وسائل الدفع المخصصة")

    # Tracking daily usage
    daily_deposit_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    daily_withdrawal_usage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    last_limit_reset = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["status"]),
            models.Index(fields=["tier"]),
        ]
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        full_name = self.get_full_name()
        return full_name if full_name else self.email

    def reset_daily_limits_if_needed(self):
        """Resets daily usage if 24 hours have passed since last reset."""
        now = timezone.now()
        if (now - self.last_limit_reset).days >= 1 or self.last_limit_reset.date() < now.date():
            self.daily_deposit_usage = Decimal("0.00")
            self.daily_withdrawal_usage = Decimal("0.00")
            self.last_limit_reset = now
            self.save(update_fields=["daily_deposit_usage", "daily_withdrawal_usage", "last_limit_reset"])

    @property
    def remaining_deposit_limit(self):
        self.reset_daily_limits_if_needed()
        return max(Decimal("0.00"), self.daily_deposit_limit - self.daily_deposit_usage)

    @property
    def remaining_withdrawal_limit(self):
        self.reset_daily_limits_if_needed()
        return max(Decimal("0.00"), self.daily_withdrawal_limit - self.daily_withdrawal_usage)

    @property
    def is_platform_staff(self):
        return self.role != self.Role.CUSTOMER or self.is_staff or self.is_superuser

    @property
    def is_account_active(self):
        if not self.is_active:
            return False
        if self.status == self.Status.BANNED:
            return False
        if self.status == self.Status.SUSPENDED:
            if self.is_permanently_suspended:
                return False
            if self.suspension_expires_at and self.suspension_expires_at > timezone.now():
                return False
        return True


class ModerationLog(TimeStampedModel):
    user = models.ForeignKey(User, related_name="moderation_history", on_delete=models.CASCADE, verbose_name="المستخدم المستهدف")
    moderator = models.ForeignKey(User, related_name="performed_moderations", on_delete=models.SET_NULL, null=True, verbose_name="المشرف")
    action = models.CharField(max_length=100, verbose_name="الإجراء")
    previous_state = models.JSONField(default=dict, blank=True, verbose_name="الحالة السابقة")
    new_state = models.JSONField(default=dict, blank=True, verbose_name="الحالة الجديدة")
    reason = models.TextField(verbose_name="السبب")
    internal_notes = models.TextField(blank=True, verbose_name="ملاحظات داخلية")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل إشراف"
        verbose_name_plural = "سجلات الإشراف"


class ActivityLog(TimeStampedModel):
    user = models.ForeignKey(User, related_name="activities", on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل نشاط"
        verbose_name_plural = "سجلات النشاط"


class UserSession(TimeStampedModel):
    user = models.ForeignKey(User, related_name="device_sessions", on_delete=models.CASCADE)
    refresh_jti = models.CharField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.ip_address or 'unknown'}"


class SecurityEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        PASSWORD_RESET = "password_reset", "Password reset"
        SUSPICIOUS_LOGIN = "suspicious_login", "Suspicious login"
        ADMIN_ACTION = "admin_action", "Admin action"

    user = models.ForeignKey(User, related_name="security_events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.user.email}"


class EmailVerificationToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    token = models.CharField(max_length=100, unique=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.token}"


class KYCRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "تم التوثيق"
        REJECTED = "rejected", "مرفوض"

    class DocumentType(models.TextChoices):
        NATIONAL_ID = "id", "الهوية الوطنية"
        PASSPORT = "passport", "جواز السفر"
        DRIVER_LICENSE = "license", "رخصة القيادة"

    class Gender(models.TextChoices):
        MALE = "male", "ذكر"
        FEMALE = "female", "أنثى"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="kyc_request")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Personal Info
    nationality = models.CharField(max_length=2, choices=COUNTRIES, verbose_name="الجنسية")
    id_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الهوية / الوثيقة")
    issuing_country = models.CharField(max_length=2, choices=COUNTRIES, verbose_name="بلد إصدار الوثيقة")
    first_name = models.CharField(max_length=100, verbose_name="الاسم الأول")
    father_name = models.CharField(max_length=100, verbose_name="اسم الأب")
    last_name = models.CharField(max_length=100, verbose_name="النسبة / الكنية")
    mother_name = models.CharField(max_length=255, default="", verbose_name="اسم الأم بالكامل")
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE, verbose_name="الجنس")
    date_of_birth = models.DateField(verbose_name="تاريخ الميلاد")
    place_of_birth = models.CharField(max_length=255, verbose_name="مكان الميلاد")
    current_residence = models.TextField(verbose_name="عنوان الإقامة الحالي")
    
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, verbose_name="نوع الوثيقة")
    
    # Images
    identity_front = models.ImageField(upload_to="kyc/front/", verbose_name="وجه الوثيقة")
    identity_back = models.ImageField(upload_to="kyc/back/", verbose_name="ظهر الوثيقة")
    selfie_verification = models.ImageField(upload_to="kyc/selfie/", verbose_name="صورة سيلفي مع الوثيقة")
    
    # Admin review
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_kycs")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض")

    class Meta:
        verbose_name = "طلب توثيق هوية"
        verbose_name_plural = "طلبات توثيق الهوية"

    def __str__(self):
        return f"KYC: {self.user.email} ({self.get_status_display()})"


class KYCSettings(TimeStampedModel):
    """Global KYC and Limit Settings."""
    # Unverified defaults
    unverified_daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("100.00"), verbose_name="حد إيداع غير الموثقين")
    unverified_daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("100.00"), verbose_name="حد سحب غير الموثقين")
    
    # Verified defaults
    verified_daily_deposit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد إيداع الموثقين")
    verified_daily_withdrawal_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("10000.00"), verbose_name="حد سحب الموثقين")
    
    # Restricted Countries
    restricted_countries = models.JSONField(default=list, blank=True, verbose_name="الدول المحظورة (قائمة رموز ISO)")
    block_by_nationality = models.BooleanField(default=True, verbose_name="حظر حسب الجنسية")
    block_by_issuing_country = models.BooleanField(default=True, verbose_name="حظر حسب بلد إصدار الوثيقة")

    class Meta:
        verbose_name = "إعدادات التوثيق والحدود"
        verbose_name_plural = "إعدادات التوثيق والحدود"

    def __str__(self):
        return "إعدادات التوثيق العالمية"

    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj


class OTPToken(TimeStampedModel):
    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        LOGIN = "login", "Login"
        PASSWORD_RESET = "password_reset", "Password Reset"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_tokens")
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.code} ({self.purpose})"
