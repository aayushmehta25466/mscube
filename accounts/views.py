from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from allauth.account.views import LoginView, SignupView, PasswordResetView
from .models import User, Member, Trainer, Staff, AdminProfile
from .utils import get_user_role, get_user_profile, get_dashboard_url


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
    """Update user profile information."""
    template_name = 'accounts/profile_update.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_profile'] = get_user_profile(self.request.user)
        return context
    
    def post(self, request, *args, **kwargs):
        user = request.user
        profile = get_user_profile(user)
        
        # Update user info
        user.full_name = request.POST.get('full_name', user.full_name)
        user.phone = request.POST.get('phone', user.phone)
        user.save()
        
        # Update profile info if exists
        if profile:
            if hasattr(profile, 'date_of_birth'):
                dob = request.POST.get('date_of_birth')
                if dob:
                    profile.date_of_birth = dob
            
            if hasattr(profile, 'address'):
                profile.address = request.POST.get('address', profile.address)
            
            # Role-specific fields
            if hasattr(profile, 'emergency_contact'):
                profile.emergency_contact = request.POST.get('emergency_contact', profile.emergency_contact)
            
            if hasattr(profile, 'specialization'):
                profile.specialization = request.POST.get('specialization', profile.specialization)
                profile.bio = request.POST.get('bio', profile.bio)
            
            if hasattr(profile, 'department'):
                profile.department = request.POST.get('department', profile.department)
            
            profile.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('accounts_profile')

