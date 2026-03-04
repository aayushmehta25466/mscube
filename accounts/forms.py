from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from .models import Member, Trainer, Staff, AdminProfile

User = get_user_model()


class UserProfileUpdateForm(forms.ModelForm):
    """Form for updating basic user information."""
    
    class Meta:
        model = User
        fields = ['full_name', 'phone']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Full Name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': '+977 1234567890'
            }),
        }


class MemberProfileUpdateForm(forms.ModelForm):
    """Form for updating member profile information."""
    
    class Meta:
        model = Member
        fields = ['date_of_birth', 'address', 'emergency_contact']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Full Address'
            }),
            'emergency_contact': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Emergency Contact Name and Phone Number'
            }),
        }
        labels = {
            'date_of_birth': 'Date of Birth',
            'address': 'Address',
            'emergency_contact': 'Emergency Contact'
        }


class TrainerProfileUpdateForm(forms.ModelForm):
    """Form for updating trainer profile information."""
    
    class Meta:
        model = Trainer
        fields = ['date_of_birth', 'address', 'specialization', 'experience_years', 'bio']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Full Address'
            }),
            'specialization': forms.TextInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'e.g., Weight Training, Yoga, CrossFit'
            }),
            'experience_years': forms.NumberInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Years of Experience'
            }),
            'bio': forms.Textarea(attrs={
                'rows': 5,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Brief biography and qualifications'
            }),
        }


class StaffProfileUpdateForm(forms.ModelForm):
    """Form for updating staff profile information."""
    
    class Meta:
        model = Staff
        fields = ['date_of_birth', 'address', 'department']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Full Address'
            }),
            'department': forms.TextInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'e.g., Front Desk, Maintenance, Sales'
            }),
        }


class AdminProfileUpdateForm(forms.ModelForm):
    """Form for updating admin profile information."""
    
    class Meta:
        model = AdminProfile
        fields = ['date_of_birth', 'address']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Full Address'
            }),
        }


class CustomPasswordChangeForm(DjangoPasswordChangeForm):
    """Custom password change form with styled widgets."""
    
    old_password = forms.CharField(
        label='Current Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Enter current password',
            'autocomplete': 'current-password'
        }),
    )
    new_password1 = forms.CharField(
        label='New Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password'
        }),
        help_text='Password must be at least 8 characters long.',
    )
    new_password2 = forms.CharField(
        label='Confirm New Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password'
        }),
    )
