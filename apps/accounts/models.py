from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.accounts.managers import UserManager
from apps.common.models import TimeStampedModel


class User(AbstractUser, TimeStampedModel):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "مدير عام"
        ADMIN = "admin", "مدير"
        MODERATOR = "moderator", "مشرف"
        FINANCE = "finance", "مالية"
        SUPPORT = "support", "دعم"
        EMPLOYEE = "employee", "موظف"
        CUSTOMER = "customer", "عميل"

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "موقوف مؤقتاً"
        FROZEN = "frozen", "مجمد"
        RESTRICTED = "restricted", "مقيد"
        UNDER_REVIEW = "under_review", "قيد المراجعة"
        BANNED = "banned", "محظور نهائياً"

    class Tier(models.TextChoices):
        BRONZE = "bronze", "برونزي"
        SILVER = "silver", "فضي"
        GOLD = "gold", "ذهبي"
        VIP = "vip", "VIP"

    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.CUSTOMER)
    
    # Tiers
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.BRONZE, verbose_name="الفئة")
    
    # Account Status & Moderation
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE, verbose_name="حالة الحساب")
    restriction_withdrawals = models.BooleanField(default=False, verbose_name="تقييد السحب")
    restriction_deposits = models.BooleanField(default=False, verbose_name="تقييد الإيداع")
    restriction_purchases = models.BooleanField(default=False, verbose_name="تقييد الشراء")
    
    suspension_reason = models.TextField(blank=True, verbose_name="سبب الإيقاف (للمستخدم)")
    admin_notes = models.TextField(blank=True, verbose_name="ملاحظات المشرف (داخلية)")
    suspension_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ انتهاء الإيقاف")
    is_permanently_suspended = models.BooleanField(default=False, verbose_name="إيقاف نهائي")

    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)

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
        return self.email

    @property
    def is_platform_staff(self):
        return self.role != self.Role.CUSTOMER or self.is_staff or self.is_superuser

    @property
    def is_account_active(self):
        if self.status == self.Status.BANNED:
            return False
        if self.status == self.Status.SUSPENDED:
            if self.is_permanently_suspended:
                return False
            if self.suspension_expires_at and self.suspension_expires_at > timezone.now():
                return False
        return self.is_active


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
