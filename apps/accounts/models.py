from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.managers import UserManager
from apps.common.models import TimeStampedModel


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "مدير عام"
        ADMIN = "admin", "مدير"
        MODERATOR = "moderator", "مشرف"
        FINANCE = "finance", "مالية"
        SUPPORT = "support", "دعم"
        EMPLOYEE = "employee", "موظف"
        CUSTOMER = "customer", "عميل"

    username = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.CUSTOMER)
    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return self.email

    @property
    def is_platform_staff(self):
        return self.role != self.Role.CUSTOMER or self.is_staff or self.is_superuser


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
