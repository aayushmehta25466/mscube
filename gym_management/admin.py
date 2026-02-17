from django.contrib import admin
from django.utils.html import format_html
from .models import MembershipPlan, Subscription, Payment, Attendance


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
        updated = queryset.update(status='active')
        self.message_user(request, f"{updated} subscriptions activated.")
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


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin for Payments."""
    
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
    
    readonly_fields = ('transaction_id', 'initiated_at', 'completed_at')
    
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
        for payment in queryset.filter(status='pending'):
            payment.mark_completed()
            count += 1
        self.message_user(request, f"{count} payments marked as completed.")
    mark_as_completed.short_description = "Mark selected payments as completed"
    
    def mark_as_failed(self, request, queryset):
        count = 0
        for payment in queryset.filter(status='pending'):
            payment.mark_failed("Marked failed by admin")
            count += 1
        self.message_user(request, f"{count} payments marked as failed.")
    mark_as_failed.short_description = "Mark selected payments as failed"


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
