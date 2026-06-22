from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from apps.accounts.models import User
from apps.common.tenant_utils import bypass_tenant_filter
import logging
import traceback

logger = logging.getLogger(__name__)


class MyAccountAdapter(DefaultAccountAdapter):
    def clean_username(self, username, shallow=False):
        with bypass_tenant_filter():
            return super().clean_username(username, shallow)

    def clean_email(self, email):
        from allauth.account.utils import filter_users_by_email
        with bypass_tenant_filter():
            if filter_users_by_email(email):
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
        debug_log_path = r"C:\Users\a0947\Documents\store\debug_social_login.log"
        
        email = sociallogin.user.email
        if not email and sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email

        try:
            with open(debug_log_path, "a", encoding="utf-8") as f:
                f.write(f"--- pre_social_login started ---\n")
                f.write(f"Email from sociallogin: {email}\n")
                f.write(f"sociallogin.is_existing before lookup: {sociallogin.is_existing}\n")
                
                # Check email list
                email_addresses = [e.email for e in sociallogin.email_addresses]
                f.write(f"sociallogin.email_addresses: {email_addresses}\n")
        except Exception:
            pass

        if not email:
            try:
                with open(debug_log_path, "a", encoding="utf-8") as f:
                    f.write("No email found, returning.\n")
            except Exception: pass
            return

        with bypass_tenant_filter():
            try:
                # Let's inspect database users matching email
                matching_users = list(User.objects.filter(email__iexact=email))
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        f.write(f"Matching users in DB: {[u.username for u in matching_users]}\n")
                except Exception: pass

                if not matching_users:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8") as f:
                            f.write("No matching user found in DB. Proceeding with signup.\n")
                    except Exception: pass
                    return
                
                user = matching_users[0]
                
                # 1. Link social account if not already connected
                if not sociallogin.is_existing:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8") as f:
                            f.write(f"Connecting social account to user ID {user.id}...\n")
                    except Exception: pass
                    
                    sociallogin.connect(request, user)
                    
                    try:
                        with open(debug_log_path, "a", encoding="utf-8") as f:
                            f.write(f"Successfully connected! sl.is_existing is now: {sociallogin.is_existing}\n")
                    except Exception: pass
                else:
                    try:
                        with open(debug_log_path, "a", encoding="utf-8") as f:
                            f.write(f"Social login is already marked as existing. Skipping connect.\n")
                    except Exception: pass
                
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
                    try:
                        with open(debug_log_path, "a", encoding="utf-8") as f:
                            f.write(f"Updated user email_verified and is_active.\n")
                    except Exception: pass
                
                # 3. Update allauth's EmailAddress record
                EmailAddress.objects.update_or_create(
                    user=user,
                    email=user.email,
                    defaults={'verified': True, 'primary': True}
                )
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        f.write(f"Updated EmailAddress record in DB.\n")
                except Exception: pass
                
            except Exception as e:
                err_msg = traceback.format_exc()
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as f:
                        f.write(f"ERROR: Exception occurred in pre_social_login:\n{err_msg}\n")
                except Exception: pass

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
