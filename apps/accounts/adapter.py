from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from apps.accounts.models import User
from apps.common.tenant_utils import bypass_tenant_filter
import logging

logger = logging.getLogger(__name__)


class MyAccountAdapter(DefaultAccountAdapter):
    def clean_username(self, username, shallow=False):
        with bypass_tenant_filter():
            return super().clean_username(username, shallow)

    def clean_email(self, email):
        from allauth.account.utils import filter_users_by_email
        with bypass_tenant_filter():
            if filter_users_by_email(email).exists():
                raise self.validation_error("email_taken")
        return email

    def populate_username(self, request, user):
        with bypass_tenant_filter():
            return super().populate_username(request, user)

    def generate_unique_username(self, txts, regex=None):
        with bypass_tenant_filter():
            return super().generate_unique_username(txts, regex)


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Connect existing accounts by email automatically and ensure they are verified.
        """
        email = sociallogin.user.email
        if not email:
            return

        with bypass_tenant_filter():
            try:
                user = User.objects.get(email__iexact=email)
                
                # 1. Link social account if not already connected
                if not sociallogin.is_existing:
                    sociallogin.connect(request, user)
                    sociallogin.is_existing = True  # Ensure in-memory state is updated to login directly
                    logger.info(f"Connected existing user {email} to social account.")
                
                # 2. Mark as verified (Google emails are trusted)
                needs_save = False
                if not user.email_verified:
                    user.email_verified = True
                    needs_save = True
                
                if not user.is_active:
                    user.is_active = True
                    needs_save = True
                
                if needs_save:
                    user.save(update_fields=["email_verified", "is_active"])
                
                # 3. Update allauth's EmailAddress record
                EmailAddress.objects.update_or_create(
                    user=user,
                    email=user.email,
                    defaults={'verified': True, 'primary': True}
                )
                
            except User.DoesNotExist:
                pass

    def save_user(self, request, sociallogin, form=None):
        """
        Called when a new user is being saved via social signup.
        """
        with bypass_tenant_filter():
            user = super().save_user(request, sociallogin, form)
            
            # Ensure phone is None instead of empty string to avoid unique constraint issues
            if not user.phone:
                user.phone = None
                
            # For social signups, we trust the provider (Google)
            user.email_verified = True
            user.is_active = True
            user.save(update_fields=["email_verified", "is_active", "phone"])
            
            # Also ensure the EmailAddress model in allauth is marked as verified
            EmailAddress.objects.get_or_create(
                user=user,
                email=user.email,
                defaults={'verified': True, 'primary': True}
            )
            
            return user

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        logger.error(f"Social authentication error for {provider_id}: {error} | {exception}")
