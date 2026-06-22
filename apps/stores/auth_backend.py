from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from apps.common.tenant_utils import get_current_store, bypass_tenant_filter

class TenantModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        
        with bypass_tenant_filter():
            try:
                # Retrieve user across all tenants using all_objects
                user = UserModel.all_objects.get(**{UserModel.USERNAME_FIELD + '__iexact': username})
            except UserModel.DoesNotExist:
                # Mitigate timing attacks
                UserModel().set_password(password)
                return None
            else:
                if user.check_password(password) and self.user_can_authenticate(user):
                    # 1. Super admins and staff can log in anywhere
                    if user.role == 'super_admin' or user.is_superuser or user.is_staff:
                        return user
                    
                    active_store = get_current_store()
                    if active_store is not None:
                        # 2. For tenant storefronts/dashboards, verify if customer, employee, or owner
                        if user.store == active_store or active_store.owner_id == user.pk:
                            return user
                        if user.store_employments.filter(store=active_store).exists():
                            return user
                        return None
                    else:
                        # 3. For main site, user must be a main platform user (store is null) or a store owner
                        if user.store is None or user.owned_stores.exists():
                            return user
                        return None
        return None

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            # Use all_objects to bypass tenant filtering when retrieving user from session
            user = UserModel.all_objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None


from allauth.account.auth_backends import AuthenticationBackend as AllauthAuthenticationBackend

class TenantAuthenticationBackend(AllauthAuthenticationBackend):
    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            # Use all_objects to bypass tenant filtering when retrieving user from session
            user = UserModel.all_objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

