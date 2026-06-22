from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.shortcuts import redirect
from apps.accounts.models import User
import logging

logger = logging.getLogger(__name__)


class MyAccountAdapter(DefaultAccountAdapter):
    def clean_username(self, username, shallow=False):
        for validator in self.get_username_validators():
            validator(username)

        username_blacklist_lower = [
            ub.lower() for ub in self.get_username_blacklist()
        ]
        if username.lower() in username_blacklist_lower:
            raise self.validation_error("username_blacklisted")
            
        if not shallow:
            # We use _base_manager to check globally across all stores, completely thread-safe
            if User._base_manager.filter(username__iexact=username).exists():
                raise self.validation_error("username_taken")
        return username

    def clean_email(self, email):
        # We use _base_manager to check globally across all stores, completely thread-safe
        if User._base_manager.filter(email__iexact=email).exists():
            raise self.validation_error("email_taken")
        return email

    def populate_username(self, request, user):
        from allauth.account.utils import user_field, user_email, user_username
        first_name = user_field(user, "first_name")
        last_name = user_field(user, "last_name")
        email = user_email(user)
        username = user_username(user)
        
        if not username:
            username = self.generate_unique_username(
                [first_name, last_name, email, "user"]
            )
            user_username(user, username)

    def generate_unique_username(self, txts, regex=None):
        from allauth.utils import generate_username_candidates, _generate_unique_username_base
        
        base_username = _generate_unique_username_base(txts, regex)
        candidates = generate_username_candidates(base_username)
        
        # Query database globally using User._base_manager
        existing_usernames_q = User._base_manager.filter(
            username__in=[c.lower() for c in candidates]
        ).values_list("username", flat=True)
        
        existing_usernames = {n.lower() for n in existing_usernames_q}
        
        # Find the first candidate that is not taken
        for candidate in candidates:
            if candidate.lower() not in existing_usernames:
                try:
                    return self.clean_username(candidate, shallow=True)
                except Exception:
                    pass
                    
        # If all candidates are taken, generate a random one
        import random
        while True:
            candidate = f"{base_username}{random.randint(1000, 9999)}"
            if not User._base_manager.filter(username__iexact=candidate).exists():
                return candidate


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Connect existing accounts by email automatically and ensure they are verified.
        """
        email = sociallogin.user.email
        if not email and sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email

        if not email:
            return

        try:
            # We use User._base_manager to get the user globally across all stores,
            # completely bypassing any tenant filters safely in any thread/context.
            user = User._base_manager.get(email__iexact=email)
            
            # 1. Link social account if not already connected
            if not sociallogin.is_existing:
                sociallogin.connect(request, user)
                logger.info(f"Connected existing user {email} to social account.")
            
            # 2. Mark as verified (Google emails are trusted) and active
            needs_save = False
            if not user.email_verified:
                user.email_verified = True
                needs_save = True
            
            if not user.is_active:
                user.is_active = True
                needs_save = True
            
            active_store = getattr(request, 'store', None)
            if active_store and not (user.is_superuser or user.is_staff or user.role == 'super_admin'):
                if user.store_id != active_store.pk:
                    messages.error(request, "This account is not linked to the current store.")
                    raise ImmediateHttpResponse(redirect("site_login"))

            if needs_save:
                fields = ["email_verified", "is_active"]
                user.save(update_fields=fields)
            
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

        # Ensure phone is None instead of empty string to avoid unique constraint issues
        if not user.phone:
            user.phone = None
            
        # Associate the new user with the active store context
        active_store = getattr(request, 'store', None)
        if active_store:
            user.store = active_store
            
        # For social signups, we trust the provider (Google)
        user.email_verified = True
        user.is_active = True
        
        fields = ["email_verified", "is_active", "phone"]
        if active_store:
            fields.append("store")
            
        user.save(update_fields=fields)
        
        # Also ensure the EmailAddress model in allauth is marked as verified
        EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'verified': True, 'primary': True}
        )
        
        return user

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        logger.error(f"Social authentication error for {provider_id}: {error} | {exception}")
