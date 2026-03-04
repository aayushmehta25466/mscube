import logging

from django.core.exceptions import PermissionDenied

from accounts.utils import get_user_role, can_manage_users, can_manage_payments


audit_logger = logging.getLogger('security.audit')


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class ObjectOwnershipMixin:
    required_admin_permission = None
    audit_object_name = 'object'

    def has_object_permission(self, obj):
        user = self.request.user

        if not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not hasattr(user, 'adminprofile'):
            return False

        if self.required_admin_permission == 'can_manage_users':
            return can_manage_users(user)
        if self.required_admin_permission == 'can_manage_payments':
            return can_manage_payments(user)

        return True

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        allowed = self.has_object_permission(obj)

        audit_logger.warning(
            "SENSITIVE_OBJECT_ACCESS | user=%s | role=%s | object_type=%s | object_id=%s | allowed=%s | path=%s | ip=%s",
            self.request.user.email,
            get_user_role(self.request.user),
            self.audit_object_name,
            getattr(obj, 'pk', None),
            allowed,
            self.request.path,
            get_client_ip(self.request),
        )

        if not allowed:
            raise PermissionDenied('You do not have permission to access this resource.')

        return obj
