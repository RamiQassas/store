from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.shortcuts import redirect
from apps.accounts.models import User
import logging

logger = logging.getLogger(__name__)


def extract_strings(obj):
    if isinstance(obj, str):
        return [obj]
    elif isinstance(obj, dict):
        strings = []
        for k, v in obj.items():
            strings.extend(extract_strings(k))
            strings.extend(extract_strings(v))
        return strings
    elif isinstance(obj, (list, tuple, set)):
        strings = []
        for item in obj:
            strings.extend(extract_strings(item))
        return strings
    return []


def get_store_from_request(request):
    if getattr(request, 'store', None):
        return request.store
        
    import re
    from urllib.parse import unquote
    from apps.stores.models import Store
    from apps.common.tenant_utils import bypass_tenant_filter
    
    candidates = []
    
    # Check request parameters
    for k, v in request.GET.items():
        candidates.extend(extract_strings(v))
    for k, v in request.POST.items():
        candidates.extend(extract_strings(v))
        
    # Check session
    if hasattr(request, 'session'):
        for k, v in request.session.items():
            candidates.extend(extract_strings(v))
                
    for val in candidates:
        if not val or not isinstance(val, str):
            continue
        # Decode the value to handle URL-encoded URLs (e.g. inside next parameter)
        decoded_val = unquote(val)
        # Find all occurrences of subdomain pattern
        matches = re.findall(r'https?://([^./]+)\.(?:raqamiyatapp\.com|localhost|testserver)', decoded_val, re.IGNORECASE)
        for subdomain in matches:
            if subdomain.lower() not in ["www", "raqamiyatapp"]:
                with bypass_tenant_filter():
                    try:
                        return Store.objects.get(subdomain__iexact=subdomain)
                    except Store.DoesNotExist:
                        pass
                        
    return None


class MyAccountAdapter(DefaultAccountAdapter):
    def clean_username(self, username, shallow=False):
        username = super().clean_username(username, shallow=shallow)
        
        if not shallow:
            active_store = get_store_from_request(self.request)
            if active_store:
                exists = User._base_manager.filter(username__iexact=username, store=active_store).exists()
            else:
                exists = User._base_manager.filter(username__iexact=username, store__isnull=True).exists()
            
            if exists:
                raise self.validation_error("username_taken")
        return username

    def clean_email(self, email):
        active_store = get_store_from_request(self.request)
        if active_store:
            exists = User._base_manager.filter(email__iexact=email, store=active_store).exists()
        else:
            exists = User._base_manager.filter(email__iexact=email, store__isnull=True).exists()
            
        if exists:
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
    def get_app(self, request, provider, client_id=None):
        app = super().get_app(request, provider, client_id=client_id)
        if provider == "google":
            from django.conf import settings
            valid_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
            valid_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
            if valid_id and ("dgh580lvgds8" in app.client_id or app.client_id != valid_id):
                logger.info(f"Dynamically updating Google SocialApp client_id from {app.client_id} to {valid_id}")
                app.client_id = valid_id
                if valid_secret:
                    app.secret = valid_secret
                try:
                    app.save(update_fields=["client_id", "secret"])
                except Exception as e:
                    logger.warning(f"Failed to save updated SocialApp: {e}")
        return app

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
            active_store = get_store_from_request(request)
            
            # Find the existing user using robust fallback logic:
            # 1. First, search for user in active_store if active_store is set
            user = None
            if active_store:
                try:
                    user = User._base_manager.get(email__iexact=email, store=active_store)
                except User.DoesNotExist:
                    pass
            
            # 2. If user is not found or active_store is None, try to find a user globally
            if not user:
                users = User._base_manager.filter(email__iexact=email)
                if users.count() == 1:
                    user = users.first()
                elif users.count() > 1:
                    if active_store:
                        user = users.filter(store=active_store).first()
                    else:
                        user = users.filter(store__isnull=True).first()

            if not user:
                raise User.DoesNotExist
            
            # 1. Link social account if not already connected
            if not sociallogin.is_existing:
                sociallogin.connect(request, user)
                # Force is_existing flag just in case the version of allauth checks it as a boolean attribute
                try:
                    sociallogin.is_existing = True
                except AttributeError:
                    pass
                logger.info(f"Connected existing user {email} to social account in store/global context.")
            
            # 2. Mark as verified (Google emails are trusted) and active
            needs_save = False
            if not user.email_verified:
                user.email_verified = True
                needs_save = True
            
            if not user.is_active:
                user.is_active = True
                needs_save = True

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
        active_store = get_store_from_request(request)
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
