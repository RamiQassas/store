from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from apps.accounts.models import User

def role_required(allowed_roles):
    """
    Decorator for views that checks whether the user has one of the allowed roles.
    Superadmins always have access.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('site_login')
            
            # Subdomain store context
            active_store = getattr(request, 'store', None)
            if active_store:
                is_store_member = (
                    active_store.owner_id == request.user.pk or
                    request.user.store_id == active_store.pk or
                    request.user.store_employments.filter(store=active_store).exists()
                )
                if is_store_member:
                    return view_func(request, *args, **kwargs)
                raise PermissionDenied

            if request.user.is_superuser or request.user.role == User.Role.SUPER_ADMIN:
                return view_func(request, *args, **kwargs)
            
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied
        return _wrapped_view
    return decorator

# Specific Role Decorators
def staff_required(view_func):
    return role_required([User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.SUPPORT, User.Role.FINANCE, User.Role.MODERATOR])(view_func)

def super_admin_required(view_func):
    return role_required([User.Role.SUPER_ADMIN])(view_func)

def admin_required(view_func):
    return role_required([User.Role.SUPER_ADMIN, User.Role.ADMIN])(view_func)

def finance_required(view_func):
    return role_required([User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.FINANCE])(view_func)

def support_required(view_func):
    return role_required([User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.SUPPORT])(view_func)

def kyc_required(view_func):
    return role_required([User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.MODERATOR])(view_func)
