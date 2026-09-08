from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from apps.common.tenant_utils import get_current_store, bypass_tenant_filter

class TenantModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD) or kwargs.get("email") or kwargs.get("username")
        
        if not username or not password:
            return None

        # Determine active store from request or context
        active_store = None
        if request and hasattr(request, 'store') and request.store:
            active_store = request.store
        if active_store is None:
            active_store = get_current_store()

        with bypass_tenant_filter():
            lookup = {f"{UserModel.USERNAME_FIELD}__iexact": username}
            candidates = list(UserModel.all_objects.filter(**lookup))
            if not candidates and UserModel.USERNAME_FIELD != "email":
                candidates = list(UserModel.all_objects.filter(email__iexact=username))

            if not candidates:
                # Mitigate timing attacks
                UserModel().set_password(password)
                return None

            # Prioritize candidates based on active_store context:
            def get_user_priority(u):
                if active_store is not None:
                    if u.store_id == active_store.pk:
                        return 0  # Highest priority: tenant store direct user
                    if active_store.owner_id == u.pk:
                        return 1  # Tenant store owner
                    if u.store_employments.filter(store=active_store).exists():
                        return 2  # Tenant store employee
                    if u.role == 'super_admin' or u.is_superuser or u.is_staff:
                        return 3  # Superadmin / staff
                    if u.store_id is None:
                        return 4  # Main platform customer accessing sub-store
                    return 99  # User belonging to another store
                else:
                    if u.store_id is None:
                        return 0  # Highest priority: main platform user
                    if u.owned_stores.exists():
                        return 1  # Store owner accessing main platform
                    if u.role == 'super_admin' or u.is_superuser or u.is_staff:
                        return 2  # Superadmin / staff
                    return 10  # Sub-store customer accessing main platform

            candidates.sort(key=get_user_priority)

            for u in candidates:
                if get_user_priority(u) == 99:
                    continue
                if u.check_password(password) and self.user_can_authenticate(u):
                    if active_store is None and u.store_id is not None and not u.owned_stores.exists() and not (u.is_superuser or u.is_staff):
                        # User has an account in a sub-store and entered correct credentials on the main platform:
                        # Find or auto-provision their main platform user so they are not rejected by TenantMiddleware
                        main_u = UserModel.all_objects.filter(email__iexact=u.email, store__isnull=True).first()
                        if not main_u:
                            main_u = UserModel.objects.create_user(
                                email=u.email,
                                username=u.email,
                                password=password,
                                first_name=u.first_name,
                                last_name=u.last_name,
                                phone=u.phone,
                                store=None,
                                email_verified=u.email_verified,
                                is_active=True
                            )
                            from apps.wallets.services import get_or_create_wallet
                            get_or_create_wallet(main_u)
                        else:
                            if not main_u.check_password(password):
                                main_u.set_password(password)
                                main_u.save(update_fields=['password'])
                        return main_u
                    return u

            # Mitigate timing attacks
            UserModel().set_password(password)
            return None

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            with bypass_tenant_filter():
                user = UserModel.all_objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None


from allauth.account.auth_backends import AuthenticationBackend as AllauthAuthenticationBackend

class TenantAuthenticationBackend(AllauthAuthenticationBackend):
    def authenticate(self, request, **credentials):
        return TenantModelBackend().authenticate(request, **credentials)

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            with bypass_tenant_filter():
                user = UserModel.all_objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None


