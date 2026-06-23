from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_queryset(self):
        from apps.common.tenant_utils import get_current_store, is_tenant_filter_bypassed
        qs = super().get_queryset()
        
        # Safe check for early migrations where 'store' field doesn't exist yet
        try:
            self.model._meta.get_field("store")
        except Exception:
            return qs

        if is_tenant_filter_bypassed():
            return qs
        store = get_current_store()
        if store is not None:
            return qs.filter(store=store)
        return qs.filter(store__isnull=True)

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        
        username = extra_fields.get("username")
        if not username:
            store = extra_fields.get("store")
            if store:
                from django.utils.crypto import get_random_string
                email_part = email.split('@')[0][:100]
                extra_fields["username"] = f"{email_part}_{get_random_string(12)}"
            else:
                extra_fields["username"] = email
        
        # Set default limits from global settings
        from apps.accounts.models import KYCSettings
        kyc_settings = KYCSettings.get_settings()
        extra_fields.setdefault("daily_deposit_limit", kyc_settings.unverified_daily_deposit_limit)
        extra_fields.setdefault("daily_withdrawal_limit", kyc_settings.unverified_daily_withdrawal_limit)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("preferred_language", "ar")
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "super_admin")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

