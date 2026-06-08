from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True
        owner = getattr(obj, "user", None) or getattr(obj, "customer", None)
        return owner == request.user


class ReadOnlyOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class HasStaffRole(BasePermission):
    required_roles = set()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role == "super_admin":
            return True
        required_roles = getattr(view, "required_roles", self.required_roles)
        return bool(required_roles and request.user.role in required_roles)

class IsFinanceManager(BasePermission):
    def has_permission(self, request, view):
        from apps.accounts.models import User
        if not request.user or not request.user.is_authenticated: return False
        return bool(request.user.is_superuser or request.user.role in [User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.FINANCE])

class IsKYCManager(BasePermission):
    def has_permission(self, request, view):
        from apps.accounts.models import User
        if not request.user or not request.user.is_authenticated: return False
        return bool(request.user.is_superuser or request.user.role in [User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.MODERATOR])

class IsSupportAgent(BasePermission):
    def has_permission(self, request, view):
        from apps.accounts.models import User
        if not request.user or not request.user.is_authenticated: return False
        return bool(request.user.is_superuser or request.user.role in [User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.SUPPORT])
