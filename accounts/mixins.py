from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


class AdminRequiredMixin(LoginRequiredMixin):
    """Mixin to require that the user has an AdminProfile."""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if not hasattr(request.user, 'adminprofile'):
            messages.error(request, 'You do not have permission to access this page.')
            raise PermissionDenied("Admin access required.")
        
        return super().dispatch(request, *args, **kwargs)


class TrainerRequiredMixin(LoginRequiredMixin):
    """Mixin to require that the user has a Trainer profile."""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if not hasattr(request.user, 'trainer'):
            messages.error(request, 'You do not have permission to access this page.')
            raise PermissionDenied("Trainer access required.")
        
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(LoginRequiredMixin):
    """Mixin to require that the user has a Staff profile."""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if not hasattr(request.user, 'staff'):
            messages.error(request, 'You do not have permission to access this page.')
            raise PermissionDenied("Staff access required.")
        
        return super().dispatch(request, *args, **kwargs)


class MemberRequiredMixin(LoginRequiredMixin):
    """Mixin to require that the user has a Member profile."""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if not hasattr(request.user, 'member'):
            messages.error(request, 'You do not have a member profile. Please contact support.')
            raise PermissionDenied("Member access required.")
        
        return super().dispatch(request, *args, **kwargs)


class StaffOrAdminRequiredMixin(LoginRequiredMixin):
    """Mixin to require that the user is either Staff or Admin."""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if not (hasattr(request.user, 'staff') or hasattr(request.user, 'adminprofile')):
            messages.error(request, 'You do not have permission to access this page.')
            raise PermissionDenied("Staff or Admin access required.")
        
        return super().dispatch(request, *args, **kwargs)
