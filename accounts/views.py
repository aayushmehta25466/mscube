from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView, UpdateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from allauth.account.views import LoginView, SignupView, PasswordResetView
from .models import User, Member, Trainer, Staff, AdminProfile
from .utils import get_user_role, get_user_profile, get_dashboard_url
from .forms import (
    UserProfileUpdateForm,
    MemberProfileUpdateForm,
    TrainerProfileUpdateForm,
    StaffProfileUpdateForm,
    AdminProfileUpdateForm,
    CustomPasswordChangeForm,
)


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'


class CustomSignupView(SignupView):
    template_name = 'accounts/signup.html'


class CustomPasswordResetView(PasswordResetView):
    template_name = 'accounts/password_reset.html'


class ProfileView(LoginRequiredMixin, TemplateView):
    """Display user profile based on their role."""
    template_name = 'accounts/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = get_user_role(self.request.user)
        context['user_profile'] = get_user_profile(self.request.user)
        context['dashboard_url'] = get_dashboard_url(self.request.user)
        return context


@login_required
def dashboard_redirect(request):
    """Redirect to appropriate dashboard based on user role."""
    dashboard_url = get_dashboard_url(request.user)
    return redirect(dashboard_url)


class ProfileUpdateView(LoginRequiredMixin, TemplateView):
    """Update user profile information with proper form handling."""
    template_name = 'accounts/profile_update.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        profile = get_user_profile(user)
        
        # User form
        context['user_form'] = UserProfileUpdateForm(instance=user)
        
        # Role-specific form
        if hasattr(user, 'member'):
            context['profile_form'] = MemberProfileUpdateForm(instance=user.member)
            context['profile_type'] = 'member'
        elif hasattr(user, 'trainer'):
            context['profile_form'] = TrainerProfileUpdateForm(instance=user.trainer)
            context['profile_type'] = 'trainer'
        elif hasattr(user, 'staff'):
            context['profile_form'] = StaffProfileUpdateForm(instance=user.staff)
            context['profile_type'] = 'staff'
        elif hasattr(user, 'adminprofile'):
            context['profile_form'] = AdminProfileUpdateForm(instance=user.adminprofile)
            context['profile_type'] = 'admin'
        
        context['user_role'] = get_user_role(user)
        context['user_profile'] = profile
        
        return context
    
    def post(self, request, *args, **kwargs):
        user = request.user
        profile = get_user_profile(user)
        
        # User form validation
        user_form = UserProfileUpdateForm(request.POST, instance=user)
        
        # Profile form validation based on role
        profile_form = None
        if hasattr(user, 'member'):
            profile_form = MemberProfileUpdateForm(request.POST, instance=user.member)
        elif hasattr(user, 'trainer'):
            profile_form = TrainerProfileUpdateForm(request.POST, instance=user.trainer)
        elif hasattr(user, 'staff'):
            profile_form = StaffProfileUpdateForm(request.POST, instance=user.staff)
        elif hasattr(user, 'adminprofile'):
            profile_form = AdminProfileUpdateForm(request.POST, instance=user.adminprofile)
        
        if user_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            user_form.save()
            if profile_form:
                profile_form.save()
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts_profile')
        else:
            # Re-render with errors
            context = self.get_context_data()
            context['user_form'] = user_form
            if profile_form:
                context['profile_form'] = profile_form
            return self.render_to_response(context)


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Change password with custom form and redirect."""
    form_class = CustomPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts_profile')
    
    def form_valid(self, form):
        messages.success(self.request, 'Your password has been changed successfully!')
        return super().form_valid(form)

