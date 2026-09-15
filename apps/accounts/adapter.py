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


def get_store_from_request(request, sociallogin=None):
    if getattr(request, 'store', None):
        return request.store

    import re
    from urllib.parse import unquote, urlparse, parse_qs
    from apps.stores.models import Store
    from apps.common.tenant_utils import bypass_tenant_filter

    # Check direct session keys first
    if hasattr(request, 'session'):
        store_id = request.session.get('sso_target_store_id')
        if store_id:
            with bypass_tenant_filter():
                s = Store.objects.filter(pk=store_id).first()
                if s:
                    return s
        store_sub = request.session.get('sso_target_subdomain')
        if store_sub:
            with bypass_tenant_filter():
                s = Store.objects.filter(subdomain__iexact=store_sub).first()
                if s:
                    return s

    candidates = []

    # Check sociallogin if provided
    if sociallogin:
        if hasattr(sociallogin, 'state') and isinstance(sociallogin.state, dict):
            candidates.extend(extract_strings(sociallogin.state))
        if getattr(sociallogin, 'token', None):
            candidates.extend(extract_strings(getattr(sociallogin.token, 'params', {})))

    # Check request attributes
    if hasattr(request, '_sociallogin'):
        sl = getattr(request, '_sociallogin')
        if hasattr(sl, 'state') and isinstance(sl.state, dict):
            candidates.extend(extract_strings(sl.state))

    # Check request parameters
    for k, v in request.GET.items():
        candidates.extend(extract_strings(v))
    for k, v in request.POST.items():
        candidates.extend(extract_strings(v))

    # Check session
    if hasattr(request, 'session'):
        for k, v in request.session.items():
            candidates.extend(extract_strings(v))

    with bypass_tenant_filter():
        for val in candidates:
            if not val or not isinstance(val, str):
                continue
            decoded_val = unquote(val)
            urls_to_check = [decoded_val]
            # Check for nested next parameter in query string
            if 'next=' in decoded_val:
                try:
                    p = urlparse(decoded_val)
                    qs = parse_qs(p.query)
                    if 'next' in qs:
                        urls_to_check.extend([unquote(x) for x in qs['next']])
                except Exception:
                    pass

            for u in urls_to_check:
                # 1. Regex check for subdomain in domain
                sub_matches = re.findall(r'https?://([^./:]+)\.(?:raqamiyatapp\.com|localhost|testserver)', u, re.IGNORECASE)
                for sm in sub_matches:
                    if sm.lower() not in ["www", "raqamiyatapp"]:
                        store = Store.objects.filter(subdomain__iexact=sm).first()
                        if store:
                            return store

                # 2. Parse hostname
                try:
                    p = urlparse(u)
                    host = (p.hostname or p.netloc.split(':')[0]).lower()
                    if host and host not in ["raqamiyatapp.com", "www.raqamiyatapp.com", "localhost", "127.0.0.1", "testserver"]:
                        if host.endswith(".raqamiyatapp.com"):
                            sub = host[:-len(".raqamiyatapp.com")]
                            store = Store.objects.filter(subdomain__iexact=sub).first()
                            if store:
                                return store
                        store = Store.objects.filter(custom_domain__iexact=host).first()
                        if store:
                            return store
                        store = Store.objects.filter(subdomain__iexact=host).first()
                        if store:
                            return store
                except Exception:
                    pass

                # 3. Direct subdomain check
                if re.match(r'^[a-zA-Z0-9_-]{2,50}$', u):
                    if u.lower() not in ["www", "raqamiyatapp", "dashboard", "control", "admin", "auth"]:
                        store = Store.objects.filter(subdomain__iexact=u).first()
                        if store:
                            return store

    return None


class MyAccountAdapter(DefaultAccountAdapter):
    def is_login_by_code_required(self, login):
        if not getattr(self, "request", None) or not getattr(self.request, "session", None):
            return False
        return super().is_login_by_code_required(login)

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

    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        # Clean up greeting message to display user's real name instead of internal randomized username
        if message_template == 'account/messages/logged_in.txt':
            user = None
            if message_context and 'user' in message_context:
                user = message_context['user']
            elif hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
            if user:
                name = user.first_name or user.get_full_name() or (user.email.split('@')[0] if user.email else user.username)
                from django.contrib import messages
                messages.add_message(request, level, f"مرحباً بك، تم تسجيل الدخول بنجاح يا {name}.", extra_tags=extra_tags)
                return
        super().add_message(request, level, message_template, message_context=message_context, extra_tags=extra_tags)

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
            if valid_id and app.client_id != valid_id:
                logger.info(f"Dynamically updating Google SocialApp client_id from {app.client_id} to {valid_id}")
                app.client_id = valid_id
                if valid_secret:
                    app.secret = valid_secret
                try:
                    app.save(update_fields=["client_id", "secret"])
                except Exception as e:
                    logger.warning(f"Failed to save updated SocialApp: {e}")
        return app

    def is_auto_signup_allowed(self, request, sociallogin):
        return True

    def pre_social_login(self, request, sociallogin):
        """
        Connect existing accounts by email automatically, mark them verified, and perform immediate login.
        """
        email = None
        if getattr(sociallogin, "user", None) and getattr(sociallogin.user, "email", None):
            email = sociallogin.user.email
        if not email and sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email
        if not email and getattr(sociallogin, "account", None) and sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get("email")

        if not email:
            return

        email = email.strip().lower()

        try:
            active_store = get_store_from_request(request, sociallogin=sociallogin)
            
            # If logged in with a sub-store account on the main platform, decouple that session safely
            if active_store is None and request.user.is_authenticated and getattr(request.user, "store_id", None) is not None:
                from apps.common.tenant_utils import bypass_tenant_filter
                with bypass_tenant_filter():
                    is_owner = request.user.owned_stores.exists()
                if not is_owner and not (request.user.is_superuser or request.user.is_staff):
                    from django.contrib.auth.models import AnonymousUser
                    request.user = AnonymousUser()
                    if hasattr(sociallogin, "state") and isinstance(sociallogin.state, dict):
                        sociallogin.state["process"] = "login"

            user = None
            if active_store:
                from apps.common.tenant_utils import bypass_tenant_filter
                from django.db.models import Q
                with bypass_tenant_filter():
                    is_owner = bool(active_store.owner and active_store.owner.email.lower() == email)
                    admin_user = User.all_objects.filter(
                        email__iexact=email,
                        store__isnull=True
                    ).filter(
                        Q(is_superuser=True) | Q(is_staff=True) | Q(role__in=["super_admin", "admin"])
                    ).first()

                if is_owner:
                    user = active_store.owner
                elif admin_user:
                    user = admin_user
                else:
                    user = User.all_objects.filter(email__iexact=email, store=active_store).first()
                    if not user:
                        from django.utils.crypto import get_random_string
                        first_name = sociallogin.account.extra_data.get("given_name") or ""
                        last_name = sociallogin.account.extra_data.get("family_name") or ""
                        user = User.objects.create_user(
                            email=email,
                            username=email,
                            password=get_random_string(32),
                            first_name=first_name,
                            last_name=last_name,
                            store=active_store,
                            email_verified=True,
                            is_active=True
                        )
                        from apps.wallets.services import get_or_create_wallet
                        get_or_create_wallet(user)
            else:
                user = User.all_objects.filter(email__iexact=email, store__isnull=True).first()
                if not user:
                    from django.utils.crypto import get_random_string
                    first_name = sociallogin.account.extra_data.get("given_name") or ""
                    last_name = sociallogin.account.extra_data.get("family_name") or ""
                    user = User.objects.create_user(
                        email=email,
                        username=email,
                        password=get_random_string(32),
                        first_name=first_name,
                        last_name=last_name,
                        store=None,
                        email_verified=True,
                        is_active=True
                    )
                    from apps.wallets.services import get_or_create_wallet
                    get_or_create_wallet(user)

            if not user:
                return

            # Mark user as verified (Google emails are trusted) and active
            needs_save = False
            if not user.email_verified:
                user.email_verified = True
                needs_save = True
            if not user.is_active:
                user.is_active = True
                needs_save = True
            if needs_save:
                user.save(update_fields=["email_verified", "is_active"])
            
            # Ensure allauth EmailAddress record exists and is marked as verified
            EmailAddress.objects.update_or_create(
                user=user,
                email=user.email,
                defaults={'verified': True, 'primary': True}
            )

            # Link social account and save to DB
            from allauth.socialaccount.models import SocialAccount
            sociallogin.user = user
            try:
                acc = SocialAccount.objects.filter(
                    provider=sociallogin.account.provider,
                    uid=sociallogin.account.uid
                ).first()
                if not acc:
                    sociallogin.account.user = user
                    sociallogin.account.save()
                else:
                    if acc.user_id != user.id:
                        acc.user = user
                    acc.extra_data = sociallogin.account.extra_data
                    acc.save()
                    sociallogin.account = acc
                logger.info(f"Connected existing user {email} to Google social account successfully.")
            except Exception as conn_err:
                logger.warning(f"Error connecting social account in pre_social_login: {conn_err}")

            # Perform immediate login to bypass 3rdparty/signup form
            from allauth.account.utils import perform_login
            from django.conf import settings
            from django.http import HttpResponseRedirect
            from allauth.core.exceptions import ImmediateHttpResponse

            # Determine redirect URL: preserve next param from OAuth state, GET or session to return to sub-store
            next_url = None
            if hasattr(sociallogin, "state") and isinstance(sociallogin.state, dict):
                next_url = sociallogin.state.get("next")
            if not next_url:
                next_url = request.GET.get("next") or request.session.get("next") or request.session.get("sso_target_url")

            if active_store:
                from django.conf import settings
                from urllib.parse import quote
                platform_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
                target_domain = active_store.custom_domain or f"{active_store.subdomain}.raqamiyatapp.com"

                # If next_url is directly to the tenant domain (without sso-callback), wrap it so it gets an SSO token
                if next_url and (target_domain in next_url) and ("/auth/sso-callback" not in next_url):
                    next_url = f"{platform_url}/auth/sso-callback/?store_id={active_store.pk}&subdomain={active_store.subdomain}&next={quote(next_url)}"
                elif not next_url or ("/auth/sso-callback" not in next_url and target_domain not in next_url):
                    next_url = f"{platform_url}/auth/sso-callback/?store_id={active_store.pk}&subdomain={active_store.subdomain}&next=https://{target_domain}/dashboard/"

            if not next_url:
                next_url = getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/")

            resp = perform_login(
                request,
                user,
                email_verification="none",
                redirect_url=next_url
            )
            raise ImmediateHttpResponse(resp or HttpResponseRedirect(next_url))
            
        except ImmediateHttpResponse:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in pre_social_login: {e}", exc_info=True)

    def save_user(self, request, sociallogin, form=None):
        """
        Called when a new user is being saved via social signup.
        """
        user = super().save_user(request, sociallogin, form)

        # Ensure phone is None instead of empty string to avoid unique constraint issues
        if not user.phone:
            user.phone = None
            
        # Associate the new user with the active store context
        active_store = get_store_from_request(request, sociallogin=sociallogin)
        if active_store:
            from apps.common.tenant_utils import bypass_tenant_filter
            with bypass_tenant_filter():
                is_owner = bool(active_store.owner and active_store.owner.email.lower() == user.email.lower())
                is_admin = user.is_superuser or user.is_staff or getattr(user, 'role', None) in ['super_admin', 'admin']
            if not is_owner and not is_admin:
                user.store = active_store
            
        # For social signups, we trust the provider (Google)
        user.email_verified = True
        user.is_active = True
        
        fields = ["email_verified", "is_active", "phone"]
        if user.store_id:
            fields.append("store")
            
        user.save(update_fields=fields)
        
        # Also ensure the EmailAddress model in allauth is marked as verified
        EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={'verified': True, 'primary': True}
        )
        
        return user

    def get_login_redirect_url(self, request):
        next_url = request.GET.get("next") or request.session.get("next")
        if next_url:
            return next_url
        from django.conf import settings
        return getattr(settings, "LOGIN_REDIRECT_URL", "/dashboard/")

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        logger.error(f"Social authentication error for {provider_id}: {error} | {exception}")
