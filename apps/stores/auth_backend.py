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
                        # 2. For tenant storefronts/dashboards, verify if customer or employee
                        if user.store == active_store:
                            return user
                        if user.store_employments.filter(store=active_store).exists():
                            return user
                        return None
                    else:
                        # 3. For main site, user must be a main platform user (store is null)
                        if user.store is None:
                            return user
                        return None
        return None
