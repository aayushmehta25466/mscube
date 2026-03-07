from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Case, CharField, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from accounts.models import Member
from .models import MembershipPlan, Subscription, Payment, Attendance
from .services import PaymentService, SubscriptionService
from datetime import timedelta

User = get_user_model()


def normalize_model_pk(value):
    if hasattr(value, 'pk'):
        return value.pk
    return value


def get_member_subscription_status_queryset(current_member_id=None):
    current_member_id = normalize_model_pk(current_member_id)
    pending_subscriptions = Subscription.objects.filter(member=OuterRef('pk'), status='pending')
    active_subscriptions = Subscription.objects.filter(member=OuterRef('pk'), status='active')
    expired_subscriptions = Subscription.objects.filter(member=OuterRef('pk'), status='expired')
    cancelled_subscriptions = Subscription.objects.filter(member=OuterRef('pk'), status='cancelled')

    member_filter = Q(is_active=True)
    if current_member_id:
        member_filter |= Q(pk=current_member_id)

    return (
        Member.all_objects.filter(member_filter)
        .select_related('user')
        .annotate(
            has_pending_subscription=Exists(pending_subscriptions),
            has_active_subscription=Exists(active_subscriptions),
            has_expired_subscription=Exists(expired_subscriptions),
            has_cancelled_subscription=Exists(cancelled_subscriptions),
        )
        .annotate(
            subscription_status_label=Case(
                When(has_pending_subscription=True, then=Value('Pending')),
                When(has_active_subscription=True, then=Value('Active')),
                When(has_expired_subscription=True, then=Value('Expired')),
                When(has_cancelled_subscription=True, then=Value('Cancelled')),
                default=Value('No Subscription'),
                output_field=CharField(),
            ),
            subscription_status_rank=Case(
                When(has_pending_subscription=True, then=Value(0)),
                When(has_active_subscription=True, then=Value(1)),
                When(has_expired_subscription=True, then=Value(2)),
                When(has_cancelled_subscription=True, then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            ),
        )
        .order_by('subscription_status_rank', 'user__full_name')
    )


def get_subscription_payment_queryset(current_subscription_id=None):
    current_subscription_id = normalize_model_pk(current_subscription_id)
    subscription_filter = Q(status='pending')
    if current_subscription_id:
        subscription_filter |= Q(pk=current_subscription_id)

    return Subscription.objects.filter(subscription_filter).select_related('member__user', 'plan').order_by(
        'member__user__full_name',
        'plan__name',
    )


def format_member_status_label(member):
    status_label = getattr(member, 'subscription_status_label', 'No Subscription')
    if status_label == 'No Subscription':
        if member.subscriptions.filter(status='pending').exists():
            status_label = 'Pending'
        elif member.subscriptions.filter(status='active').exists():
            status_label = 'Active'
        elif member.subscriptions.filter(status='expired').exists():
            status_label = 'Expired'
        elif member.subscriptions.filter(status='cancelled').exists():
            status_label = 'Cancelled'
    return f"{member.user.full_name} ({status_label})"


def format_pending_subscription_label(subscription):
    return f"{subscription.member.user.full_name} - {subscription.plan.name} - Pending"


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


# Shared HTML5 date-picker widget attrs — used by all subscription date fields.
_DATE_INPUT_WIDGET_ATTRS = {
    'type': 'date',
    'class': (
        'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
        'focus:outline-none focus:border-primary transition-colors [color-scheme:dark]'
    ),
}


class SubscriptionBaseForm(forms.ModelForm):
    """
    Shared base for subscription creation and update flows.

    Guarantees UI consistency by providing:
    - Identical plan ModelChoiceField with price/duration label.
    - Identical start_date DateField with HTML5 date-picker widget.
    - Shared clean_start_date() that rejects past dates on new entries
      while allowing an existing subscription to retain its historical date.
    """

    plan = forms.ModelChoiceField(
        queryset=MembershipPlan.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': (
                'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                'focus:outline-none focus:border-primary transition-colors'
            ),
        }),
        label='Membership Plan',
    )
    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs=_DATE_INPUT_WIDGET_ATTRS),
    )

    class Meta:
        model = Subscription
        fields = ['plan', 'start_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].label_from_instance = lambda obj: (
            f"{obj.name}  —  NPR {obj.price:,.2f}  ({obj.duration_days} days)"
        )

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if not start_date:
            return start_date
        today = timezone.localdate()
        # Allow retaining an unchanged historical start_date on existing subscriptions.
        is_unchanged = bool(
            self.instance
            and self.instance.pk
            and self.instance.start_date == start_date
        )
        if not is_unchanged and start_date < today:
            raise forms.ValidationError('Start date cannot be in the past.')
        return start_date


class SubscriptionForm(SubscriptionBaseForm):
    """Shared form for creating and updating subscriptions."""

    member = forms.ModelChoiceField(
        queryset=Member.objects.filter(is_active=True).select_related('user'),
        widget=forms.Select(attrs={
            'class': (
                'w-full bg-dark-bg border border-border rounded-lg px-4 py-3 text-white '
                'focus:outline-none focus:border-primary transition-colors'
            ),
        }),
        label='Select Member',
    )

    class Meta(SubscriptionBaseForm.Meta):
        fields = ['member', 'plan', 'start_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_update = bool(self.instance and self.instance.pk)
        current_member_id = self.instance.member_id or self.data.get('member') or self.initial.get('member')
        self.fields['member'].queryset = get_member_subscription_status_queryset(
            current_member_id=current_member_id,
        )
        self.fields['member'].label_from_instance = format_member_status_label
        if self.is_update:
            self.fields['member'].required = False
            self.fields['member'].initial = self.instance.member
            self.fields['plan'].help_text = (
                'Changing the plan will cancel the current subscription and create a new pending subscription.'
            )

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')

        if self.is_update:
            cleaned_data['member'] = self.instance.member
            return cleaned_data

        if member:
            try:
                SubscriptionService.validate_new_subscription(member)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)

        return cleaned_data

    def save(self, commit=True):
        subscription = super().save(commit=False)
        subscription.member = self.cleaned_data.get('member') or self.instance.member
        subscription.end_date = subscription.start_date + timedelta(days=subscription.plan.duration_days)
        if not self.is_update:
            subscription.status = 'pending'

        if commit:
            if self.is_update:
                subscription.save()
                return subscription
            return SubscriptionService.create_subscription(
                member=subscription.member,
                plan=subscription.plan,
                start_date=subscription.start_date,
            )

        return subscription


SubscriptionCreateForm = SubscriptionForm
SubscriptionUpdateForm = SubscriptionForm


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
        current_subscription_id = self.instance.subscription_id or self.data.get('subscription') or self.initial.get('subscription')
        self.fields['subscription'].queryset = get_subscription_payment_queryset(
            current_subscription_id=current_subscription_id,
        )
        self.fields['subscription'].label_from_instance = format_pending_subscription_label

    def clean(self):
        cleaned_data = super().clean()
        subscription = cleaned_data.get('subscription')

        if subscription and not self.instance.pk:
            try:
                PaymentService.validate_payment_creation(subscription, exclude_payment_id=self.instance.pk)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)

        return cleaned_data

    def save(self, commit=True):
        """Override save to enforce authoritative server-side pricing.

        SECURITY: Payment amount is ALWAYS calculated from subscription plan price.
        This prevents amount tampering attacks.
        """
        payment = super().save(commit=False)
        payment.amount = payment.subscription.plan.price
        if commit:
            return PaymentService.create_payment(
                subscription=payment.subscription,
                payment_method=payment.payment_method,
            )
        return payment


class SubscriptionAdminForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ['member', 'plan', 'start_date', 'end_date', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_member_id = self.instance.member_id or self.data.get('member') or self.initial.get('member')
        self.fields['member'].queryset = get_member_subscription_status_queryset(current_member_id=current_member_id)
        self.fields['member'].label_from_instance = format_member_status_label

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')
        status = cleaned_data.get('status')

        if not self.instance.pk and status and status != 'pending':
            raise forms.ValidationError({
                'status': 'New subscriptions must start as pending until payment is completed.'
            })

        if member and status == 'active':
            try:
                SubscriptionService.validate_new_subscription(member, exclude_subscription_id=self.instance.pk)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)

            has_completed_payment = self.instance.pk and self.instance.payments.filter(status='completed').exists()
            if not has_completed_payment:
                raise forms.ValidationError({
                    'status': 'Active subscriptions require a completed payment.'
                })

        return cleaned_data


class PaymentAdminForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['subscription', 'payment_method', 'status', 'notes', 'esewa_transaction_code', 'esewa_ref_id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_subscription_id = self.instance.subscription_id or self.data.get('subscription') or self.initial.get('subscription')
        self.fields['subscription'].queryset = get_subscription_payment_queryset(
            current_subscription_id=current_subscription_id,
        )
        self.fields['subscription'].label_from_instance = format_pending_subscription_label

    def clean(self):
        cleaned_data = super().clean()
        subscription = cleaned_data.get('subscription')
        status = cleaned_data.get('status')

        if subscription and not self.instance.pk:
            try:
                PaymentService.validate_payment_creation(subscription, exclude_payment_id=self.instance.pk)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)

        if not self.instance.pk and status not in {'pending', 'completed'}:
            raise forms.ValidationError({
                'status': 'New payments must start as pending or completed.'
            })

        return cleaned_data


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
