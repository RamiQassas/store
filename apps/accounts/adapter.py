from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress
from apps.accounts.models import User
import logging

logger = logging.getLogger(__name__)

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Connect existing accounts by email automatically and ensure they are verified.
        """
        email = sociallogin.user.email
        if not email:
            return

        try:
            user = User.objects.get(email__iexact=email)
            
            # 1. Link social account if not already connected
            if not sociallogin.is_existing:
                sociallogin.connect(request, user)
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
        user = super().save_user(request, sociallogin, form)
        
        # For social signups, we trust the provider (Google)
        user.email_verified = True
        user.is_active = True
        user.save(update_fields=["email_verified", "is_active"])
        
        # Also ensure the EmailAddress model in allauth is marked as verified
        EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'verified': True, 'primary': True}
        )
        
        return user

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        logger.error(f"Social authentication error for {provider_id}: {error} | {exception}")
