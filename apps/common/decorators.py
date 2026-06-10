from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from apps.accounts.models import User

def role_required(allowed_roles):
    """
    Decorator for views that checks whether the user has one of the allowed roles.
    Superusers always have access.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('site_login')
            
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied
        return _wrapped_view
    return decorator

# Specific Role Decorators
def super_admin_required(view_func):
    # Only superusers
    return role_required([])(view_func)

def admin_required(view_func):
    return role_required([User.Role.ADMIN])(view_func)

def finance_required(view_func):
    return role_required([User.Role.ADMIN, User.Role.FINANCE])(view_func)

def support_required(view_func):
    return role_required([User.Role.ADMIN, User.Role.SUPPORT])(view_func)

def kyc_required(view_func):
    # If MODERATOR doesn't exist, we use ADMIN/SUPPORT or define it. 
    # For now, let's use ADMIN and SUPPORT.
    return role_required([User.Role.ADMIN, User.Role.SUPPORT])(view_func)
