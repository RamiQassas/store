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
            all_candidates = list(UserModel.all_objects.filter(**lookup))
            if not all_candidates and UserModel.USERNAME_FIELD != "email":
                all_candidates = list(UserModel.all_objects.filter(email__iexact=username))

            if not all_candidates:
                # Mitigate timing attacks
                UserModel().set_password(password)
                return None

            valid_candidates = []
            if active_store is not None:
                # Tenant Store context: strictly allow store direct users, store owner, employees, and platform staff
                store_pk = active_store.pk
                owner_id = active_store.owner_id

                for u in all_candidates:
                    if u.store_id == store_pk:
                        valid_candidates.append((0, u))  # Highest priority: direct tenant user
                    elif u.pk == owner_id:
                        valid_candidates.append((1, u))  # Store owner
                    elif u.store_employments.filter(store=active_store).exists():
                        valid_candidates.append((2, u))  # Store employee
                    elif u.role == 'super_admin' or u.is_superuser or u.is_staff:
                        valid_candidates.append((3, u))  # Platform admin/staff
                    elif u.store_id is None:
                        valid_candidates.append((4, u))  # Main platform customer accessing sub-store

                if not valid_candidates:
                    UserModel().set_password(password)
                    return None
            else:
                # Main Platform context: strictly allow main platform users, store owners, and platform staff
                for u in all_candidates:
                    if u.store_id is None:
                        valid_candidates.append((0, u))  # Main platform user
                    elif u.owned_stores.exists():
                        valid_candidates.append((1, u))  # Store owner accessing main platform
                    elif u.role == 'super_admin' or u.is_superuser or u.is_staff:
                        valid_candidates.append((2, u))  # Platform admin/staff

                if not valid_candidates:
                    # Account only exists in a sub-store
                    if request is not None:
                        request._sub_store_account_detected = True
                    UserModel().set_password(password)
                    return None

            # Sort by priority
            valid_candidates.sort(key=lambda item: item[0])

            for _, u in valid_candidates:
                if u.check_password(password) and self.user_can_authenticate(u):
                    return u

            # Password check failed
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


