"""
Utility functions for user profile and permission management.
"""


def get_user_role(user):
    """
    Get the role of a user based on their profile.
    
    Args:
        user: User instance
        
    Returns:
        str: 'admin', 'trainer', 'staff', 'member', or None
    """
    if not user or not user.is_authenticated:
        return None
    
    # Check in priority order
    if hasattr(user, 'adminprofile'):
        return 'admin'
    elif hasattr(user, 'trainer'):
        return 'trainer'
    elif hasattr(user, 'staff'):
        return 'staff'
    elif hasattr(user, 'member'):
        return 'member'
    
    return None


def get_user_profile(user):
    """
    Get the profile instance for a user.
    
    Args:
        user: User instance
        
    Returns:
        Profile instance (AdminProfile, Trainer, Staff, or Member) or None
    """
    if not user or not user.is_authenticated:
        return None
    
    # Check in priority order
    if hasattr(user, 'adminprofile'):
        return user.adminprofile
    elif hasattr(user, 'trainer'):
        return user.trainer
    elif hasattr(user, 'staff'):
        return user.staff
    elif hasattr(user, 'member'):
        return user.member
    
    return None


def user_has_permission(user, permission):
    """
    Check if a user has a specific admin permission.
    
    Args:
        user: User instance
        permission: str - permission name (e.g., 'can_manage_users')
        
    Returns:
        bool: True if user has the permission, False otherwise
    """
    if not user or not user.is_authenticated:
        return False
    
    # Superusers have all permissions
    if user.is_superuser:
        return True
    
    # Check if user has AdminProfile
    if hasattr(user, 'adminprofile'):
        admin_profile = user.adminprofile
        
        # Full access admins have all permissions
        if admin_profile.access_level == 'full':
            return True
        
        # Check specific permission
        return getattr(admin_profile, permission, False)
    
    return False


def can_manage_users(user):
    """Check if user can manage users."""
    return user_has_permission(user, 'can_manage_users')


def can_manage_payments(user):
    """Check if user can manage payments."""
    return user_has_permission(user, 'can_manage_payments')


def can_view_reports(user):
    """Check if user can view reports."""
    return user_has_permission(user, 'can_view_reports')


def is_admin(user):
    """Check if user has admin role."""
    return get_user_role(user) == 'admin'


def is_trainer(user):
    """Check if user has trainer role."""
    return get_user_role(user) == 'trainer'


def is_staff(user):
    """Check if user has staff role."""
    return get_user_role(user) == 'staff'


def is_member(user):
    """Check if user has member role."""
    return get_user_role(user) == 'member'


def get_dashboard_url(user):
    """
    Get the appropriate dashboard URL for a user based on their role.
    
    Args:
        user: User instance
        
    Returns:
        str: Dashboard URL path
    """
    role = get_user_role(user)
    
    if role == 'admin':
        return '/management/'
    elif role == 'trainer':
        return '/management/trainer-dashboard/'
    elif role == 'staff':
        return '/management/staff-dashboard/'
    elif role == 'member':
        return '/management/my-dashboard/'
    else:
        return '/'
