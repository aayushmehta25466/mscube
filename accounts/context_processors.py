"""
Template context processors for accounts app.
Automatically inject user role and profile data into every template context.
"""
from accounts.utils import get_user_role, get_user_profile


def user_role_context(request):
    """
    Inject user_role and user_profile into every template context automatically.
    This fixes the navbar showing "Member" for all roles.
    """
    if not request.user.is_authenticated:
        return {
            'user_role': None,
            'user_profile': None,
        }

    return {
        'user_role': get_user_role(request.user),
        'user_profile': get_user_profile(request.user),
    }
