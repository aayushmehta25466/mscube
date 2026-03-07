from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from .forms import PaymentAdminForm, SubscriptionAdminForm
from .models import MembershipPlan, Subscription, Payment, Attendance, Notification
from .services import PaymentService


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    """Admin for Membership Plans."""
    
    list_display = ('name', 'price', 'duration_days', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('price',)
    
    fieldsets = (
        ('Plan Details', {'fields': ('name', 'description', 'price', 'duration_days')}),
        ('Features', {'fields': ('features',)}),
        ('Status', {'fields': ('is_active',)}),
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin for Subscriptions."""
    form = SubscriptionAdminForm
    
    list_display = ('get_member_name', 'get_member_email', 'plan', 'start_date', 'end_date', 'status_badge', 'days_left')
    list_filter = ('status', 'start_date', 'end_date', 'plan')
    search_fields = ('member__user__username', 'member__user__email', 'member__user__full_name', 'plan__name')
    ordering = ('-created_at',)
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Subscription Details', {'fields': ('member', 'plan', 'start_date', 'end_date')}),
        ('Status', {'fields': ('status',)}),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    actions = ['activate_subscriptions', 'cancel_subscriptions', 'check_expired']
    
    def get_member_name(self, obj):
        return obj.member.user.full_name
    get_member_name.short_description = 'Member'
    
    def get_member_email(self, obj):
        return obj.member.user.email
    get_member_email.short_description = 'Email'
    
    def status_badge(self, obj):
        colors = {
            'active': 'green',
            'pending': 'orange',
            'expired': 'red',
            'cancelled': 'gray'
        }
        color = colors.get(obj.status, 'blue')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def days_left(self, obj):
        days = obj.days_remaining()
        if days > 0:
            return f"{days} days"
        return "Expired"
    days_left.short_description = 'Days Remaining'
    
    def activate_subscriptions(self, request, queryset):
        activated = 0
        blocked = 0

        for subscription in queryset.select_related('member__user', 'plan').prefetch_related('payments'):
            payment = subscription.payments.order_by('-initiated_at').first()
            if payment is None:
                blocked += 1
                continue

            try:
                PaymentService.complete_payment(payment)
            except (ValidationError, ValueError):
                blocked += 1
                continue

            activated += 1

        if activated:
            self.message_user(request, f"{activated} subscriptions activated via payment completion.")
        if blocked:
            self.message_user(
                request,
                f"{blocked} subscriptions were skipped because they do not have an eligible pending payment.",
                level=messages.WARNING,
            )
    activate_subscriptions.short_description = "Activate selected subscriptions"
    
    def cancel_subscriptions(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f"{updated} subscriptions cancelled.")
    cancel_subscriptions.short_description = "Cancel selected subscriptions"
    
    def check_expired(self, request, queryset):
        count = 0
        for subscription in queryset:
            subscription.check_expiry()
            if subscription.status == 'expired':
                count += 1
        self.message_user(request, f"{count} subscriptions marked as expired.")
    check_expired.short_description = "Check and mark expired subscriptions"
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of subscriptions - financial records must be preserved."""
        return False

    def save_model(self, request, obj, form, change):
        if not change or (obj.status == 'pending' and {'plan', 'start_date'} & set(form.changed_data)):
            obj.end_date = obj.start_date + timedelta(days=obj.plan.duration_days)
        super().save_model(request, obj, form, change)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin for Payments."""
    form = PaymentAdminForm
    
    list_display = ('transaction_id', 'get_member_name', 'amount', 'payment_method', 'status_badge', 'initiated_at', 'completed_at')
    list_filter = ('status', 'payment_method', 'initiated_at')
    search_fields = ('transaction_id', 'subscription__member__user__full_name', 'esewa_transaction_code')
    ordering = ('-initiated_at',)
    date_hierarchy = 'initiated_at'
    
    fieldsets = (
        ('Payment Details', {'fields': ('subscription', 'amount', 'payment_method', 'transaction_id')}),
        ('eSewa Information', {'fields': ('esewa_transaction_code', 'esewa_ref_id')}),
        ('Status', {'fields': ('status', 'initiated_at', 'completed_at')}),
        ('Notes', {'fields': ('notes',)}),
    )
    
    readonly_fields = ('amount', 'transaction_id', 'initiated_at', 'completed_at')
    
    actions = ['mark_as_completed', 'mark_as_failed']
    
    def get_member_name(self, obj):
        return obj.subscription.member.user.full_name
    get_member_name.short_description = 'Member'
    
    def status_badge(self, obj):
        colors = {
            'completed': 'green',
            'pending': 'orange',
            'failed': 'red',
            'refunded': 'blue'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def mark_as_completed(self, request, queryset):
        count = 0
        blocked = 0
        for payment in queryset.filter(status='pending'):
            try:
                payment.mark_completed()
            except (ValidationError, ValueError):
                blocked += 1
                continue
            count += 1
        if count:
            self.message_user(request, f"{count} payments marked as completed.")
        if blocked:
            self.message_user(
                request,
                f"{blocked} payments were skipped because the related subscription is not eligible for completion.",
                level=messages.WARNING,
            )
    mark_as_completed.short_description = "Mark selected payments as completed"
    
    def mark_as_failed(self, request, queryset):
        count = 0
        for payment in queryset.filter(status='pending'):
            payment.mark_failed("Marked failed by admin")
            count += 1
        self.message_user(request, f"{count} payments marked as failed.")
    mark_as_failed.short_description = "Mark selected payments as failed"
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payments - financial records must be preserved."""
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('subscription', 'amount', 'payment_method', 'transaction_id', 'initiated_at', 'completed_at')
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:
            payment = PaymentService.create_payment(
                subscription=form.cleaned_data['subscription'],
                payment_method=form.cleaned_data['payment_method'],
                notes=form.cleaned_data.get('notes', ''),
            )
            if form.cleaned_data.get('status') == 'completed':
                payment, _ = PaymentService.complete_payment(payment)

            obj.pk = payment.pk
            obj.transaction_id = payment.transaction_id
            obj.amount = payment.amount
            obj.status = payment.status
            obj.completed_at = payment.completed_at
            obj.initiated_at = payment.initiated_at
            return

        previous_payment = Payment.objects.get(pk=obj.pk)
        obj.amount = obj.subscription.plan.price

        if previous_payment.status != 'completed' and form.cleaned_data.get('status') == 'completed':
            obj.status = previous_payment.status
            super().save_model(request, obj, form, change)
            PaymentService.complete_payment(obj)
            return

        super().save_model(request, obj, form, change)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    """Admin for Attendance records."""
    
    list_display = ('get_member_name', 'get_member_email', 'check_in', 'check_out', 'duration_hours', 'date')
    list_filter = ('date', 'check_in')
    search_fields = ('member__user__username', 'member__user__email', 'member__user__full_name')
    ordering = ('-check_in',)
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Member', {'fields': ('member',)}),
        ('Attendance', {'fields': ('check_in', 'check_out', 'date')}),
        ('Notes', {'fields': ('notes',)}),
    )
    
    readonly_fields = ('check_in', 'date')
    
    def get_member_name(self, obj):
        return obj.member.user.full_name
    get_member_name.short_description = 'Member'
    
    def get_member_email(self, obj):
        return obj.member.user.email
    get_member_email.short_description = 'Email'
    
    def duration_hours(self, obj):
        duration = obj.duration()
        if duration:
            return f"{duration} hours"
        return "Still at gym"
    duration_hours.short_description = 'Duration'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin for Notifications."""
    
    list_display = ('get_member_name', 'notification_type', 'channel', 'title', 'is_read', 'email_sent', 'created_at')
    list_filter = ('notification_type', 'channel', 'is_read', 'email_sent', 'created_at')
    search_fields = ('member__user__full_name', 'member__user__email', 'title', 'message')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Recipient', {'fields': ('member', 'subscription')}),
        ('Notification Details', {'fields': ('notification_type', 'channel', 'title', 'message')}),
        ('Status', {'fields': ('is_read', 'read_at', 'email_sent', 'email_sent_at')}),
    )
    
    readonly_fields = ('created_at', 'read_at', 'email_sent_at')
    
    actions = ['mark_as_read', 'send_email_notifications']
    
    def get_member_name(self, obj):
        return obj.member.user.full_name
    get_member_name.short_description = 'Member'
    
    def mark_as_read(self, request, queryset):
        count = queryset.filter(is_read=False).count()
        for notification in queryset.filter(is_read=False):
            notification.mark_as_read()
        self.message_user(request, f"{count} notifications marked as read.")
    mark_as_read.short_description = "Mark selected as read"
    
    def send_email_notifications(self, request, queryset):
        from .services import NotificationService
        count = 0
        for notification in queryset.filter(email_sent=False, channel__in=['email', 'both']):
            if NotificationService.send_email_notification(notification):
                count += 1
        self.message_user(request, f"{count} email notifications sent.")
    send_email_notifications.short_description = "Send email for selected notifications"
