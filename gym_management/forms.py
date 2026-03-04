from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Member
from .models import MembershipPlan, Subscription, Payment, Attendance
from datetime import timedelta

User = get_user_model()


class MemberCreateForm(forms.ModelForm):
    """Form for creating a new member with user account."""
    
    # User fields
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Full Name'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Email Address'
        })
    )
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Username (optional - auto-generated from email)'
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': '+977 1234567890'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Password'
        })
    )
    
    # Member fields
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
        })
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Full Address'
        })
    )
    emergency_contact = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'placeholder': 'Emergency Contact Name and Phone'
        })
    )
    
    class Meta:
        model = Member
        fields = ['date_of_birth', 'address', 'emergency_contact']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username


class MemberUpdateForm(forms.ModelForm):
    """Form for updating member profile."""
    
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
        })
    )
    
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
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
            }),
            'emergency_contact': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['full_name'].initial = self.instance.user.full_name
            self.fields['phone'].initial = self.instance.user.phone


class MembershipPlanForm(forms.ModelForm):
    """Form for creating and updating membership plans."""
    
    class Meta:
        model = MembershipPlan
        fields = ['name', 'description', 'price', 'duration_days', 'features', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'e.g., Premium Monthly'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Brief description of the plan'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'NPR',
                'step': '0.01'
            }),
            'duration_days': forms.NumberInput(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'Number of days'
            }),
            'features': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
                'placeholder': 'One feature per line, e.g.:\nAccess to all equipment\nPersonal trainer sessions\nNutrition consultation'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 text-primary bg-dark-bg border-border rounded focus:ring-primary focus:ring-2'
            }),
        }


class SubscriptionCreateForm(forms.ModelForm):
    """Form for creating a subscription."""
    
    member = forms.ModelChoiceField(
        queryset=Member.objects.filter(is_active=True).select_related('user'),
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
        }),
        label='Select Member'
    )
    plan = forms.ModelChoiceField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
        }),
        label='Select Plan'
    )
    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
        })
    )
    
    class Meta:
        model = Subscription
        fields = ['member', 'plan', 'start_date']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Display member's full name in dropdown
        self.fields['member'].label_from_instance = lambda obj: f"{obj.user.full_name} ({obj.user.email})"
        # Display plan with price and duration
        self.fields['plan'].label_from_instance = lambda obj: (
            f"{obj.name}  —  NPR {obj.price:,.2f}  ({obj.duration_days} days)"
        )
    
    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')
        
        # Check if member already has an active subscription
        if member and member.subscriptions.filter(status='active').exists():
            raise forms.ValidationError(
                f'{member.user.full_name} already has an active subscription. '
                'Please cancel or wait for the current subscription to expire.'
            )
        
        return cleaned_data
    
    def save(self, commit=True):
        subscription = super().save(commit=False)
        
        # Auto-calculate end date based on plan duration
        subscription.end_date = subscription.start_date + timedelta(days=subscription.plan.duration_days)
        subscription.status = 'pending'  # Will be activated when payment is completed
        
        if commit:
            subscription.save()
        
        return subscription


class SubscriptionUpdateForm(forms.ModelForm):
    """Form for updating a subscription — shows plan, status, dates, and records a payment."""

    PAYMENT_METHOD_CHOICES = [
        ('', '— No payment (status change only) —'),
        ('cash',   'Cash'),
        ('card',   'Card / Bank Transfer'),
        ('esewa',  'eSewa'),
    ]

    plan = forms.ModelChoiceField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                     'focus:outline-none focus:border-primary transition-colors',
        }),
        label='Membership Plan',
        help_text='Changing the plan does NOT automatically create a new subscription period.',
    )

    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                     'focus:outline-none focus:border-primary transition-colors',
        }),
        label='Record Payment For This Update',
        help_text='Select a payment method to record a payment receipt alongside this update.',
    )

    class Meta:
        model = Subscription
        fields = ['plan', 'start_date', 'end_date', 'status']
        widgets = {
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                         'focus:outline-none focus:border-primary transition-colors [color-scheme:dark]',
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                         'focus:outline-none focus:border-primary transition-colors [color-scheme:dark]',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                         'focus:outline-none focus:border-primary transition-colors',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show plan with price and duration
        self.fields['plan'].label_from_instance = lambda obj: (
            f"{obj.name}  —  NPR {obj.price:,.2f}  ({obj.duration_days} days)"
        )
class PaymentCreateForm(forms.ModelForm):
    """Form for creating a payment."""
    
    subscription = forms.ModelChoiceField(
        queryset=Subscription.objects.select_related('member__user', 'plan'),
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors',
            'id': 'id_subscription',
        }),
        label='Select Subscription',
        empty_label='— Choose a subscription —',
    )
    
    class Meta:
        model = Payment
        fields = ['subscription', 'payment_method']  # SECURITY: amount calculated server-side
        widgets = {
            'payment_method': forms.Select(attrs={
                'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show pending + active subscriptions (all payable states)
        # Include enough info for admin to identify: member name, plan, price, status
        qs = Subscription.objects.filter(
            status__in=['pending', 'active']
        ).select_related('member__user', 'plan').order_by('member__user__full_name')

        self.fields['subscription'].queryset = qs

        def subscription_label(obj):
            status_label = '⏳ Pending Payment' if obj.status == 'pending' else '✅ Active'
            return (
                f"{obj.member.user.full_name}  ·  {obj.plan.name}  ·  "
                f"NPR {obj.plan.price:,.2f}  [{status_label}]"
            )

        self.fields['subscription'].label_from_instance = subscription_label

    def save(self, commit=True):
        """Override save to enforce authoritative server-side pricing.

        SECURITY: Payment amount is ALWAYS calculated from subscription plan price.
        This prevents amount tampering attacks.
        """
        payment = super().save(commit=False)
        # CRITICAL SECURITY: Always use subscription plan price - never trust client input
        payment.amount = payment.subscription.plan.price
        if commit:
            payment.save()
        return payment


class AttendanceSearchForm(forms.Form):
    """Form for searching attendance records."""
    
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
        })
    )
    member = forms.ModelChoiceField(
        queryset=Member.objects.filter(is_active=True).select_related('user'),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white focus:outline-none focus:border-primary transition-colors'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['member'].label_from_instance = lambda obj: obj.user.full_name
