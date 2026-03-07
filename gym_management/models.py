from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid
from accounts.models import Member


class MembershipPlan(models.Model):
    """Membership plans offered by the gym."""
    
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    duration_days = models.PositiveIntegerField(
        help_text="Duration of the membership in days"
    )
    features = models.TextField(
        blank=True,
        help_text="List of features (one per line or JSON)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'membership_plans'
        verbose_name = 'Membership Plan'
        verbose_name_plural = 'Membership Plans'
        ordering = ['price']
        indexes = [
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} - NPR {self.price}"


class Subscription(models.Model):
    """Member subscriptions to membership plans."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(
        MembershipPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['member', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['end_date']),
        ]
        constraints = [
            # Ensure only one active subscription per member
            models.UniqueConstraint(
                fields=['member'],
                condition=models.Q(status='active'),
                name='unique_active_subscription_per_member'
            )
        ]
    
    def __str__(self):
        return f"{self.member.user.full_name} - {self.plan.name} ({self.status})"
    
    def is_active_subscription(self):
        """Check if subscription is currently active."""
        return self.status == 'active' and self.end_date >= timezone.localdate()
    
    def days_remaining(self):
        """Calculate days remaining in subscription."""
        today = timezone.localdate()
        if self.end_date >= today:
            return (self.end_date - today).days
        return 0
    
    def activate(self):
        """Activate this subscription."""
        self.status = 'active'
        self.save()
    
    def cancel(self):
        """Cancel this subscription."""
        self.status = 'cancelled'
        self.save()
    
    def check_expiry(self):
        """Check and update subscription if expired."""
        if self.status == 'active' and self.end_date < timezone.localdate():
            self.status = 'expired'
            self.save()
    
    def delete(self, using=None, keep_parents=False):
        """Prevent deletion of subscriptions - financial records must be preserved."""
        raise ValidationError(
            f"Cannot delete subscription {self.pk}. Financial records must be preserved for audit compliance. "
            "Use cancel() to deactivate subscriptions."
        )


class Payment(models.Model):
    """Payment records for subscriptions."""
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('esewa', 'eSewa'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name='payments'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    transaction_id = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True
    )
    
    # eSewa specific fields
    esewa_transaction_code = models.CharField(max_length=255, blank=True, null=True)
    esewa_ref_id = models.CharField(max_length=255, blank=True, null=True)
    
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_method']),
        ]
    
    def __str__(self):
        return f"Payment {self.transaction_id} - NPR {self.amount} ({self.status})"
    
    def mark_completed(self):
        """Mark payment as completed."""
        from .services import PaymentService

        payment, _ = PaymentService.complete_payment(self)
        return payment
    
    def mark_failed(self, reason=''):
        """Mark payment as failed."""
        self.status = 'failed'
        if reason:
            self.notes = f"{self.notes}\nFailure reason: {reason}".strip()
        self.save()
    
    def save(self, *args, **kwargs):
        # Auto-generate secure transaction ID if not set
        if not self.transaction_id:
            for _ in range(5):
                candidate = f"TXN{uuid.uuid4().hex.upper()[:16]}"
                if not Payment.objects.filter(transaction_id=candidate).exists():
                    self.transaction_id = candidate
                    break
            if not self.transaction_id:
                raise ValueError('Unable to generate unique transaction ID.')
        super().save(*args, **kwargs)
    
    def delete(self, using=None, keep_parents=False):
        """Prevent deletion of payment records - financial records must be preserved."""
        raise ValidationError(
            f"Cannot delete payment {self.transaction_id}. Financial records must be preserved for audit compliance."
        )


class Attendance(models.Model):
    """Attendance tracking for gym members."""
    
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name='attendance_records'
    )
    check_in = models.DateTimeField(auto_now_add=True)
    check_out = models.DateTimeField(blank=True, null=True)
    date = models.DateField(auto_now_add=True)  # For easy date-based queries
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendance'
        verbose_name = 'Attendance'
        verbose_name_plural = 'Attendance Records'
        ordering = ['-check_in']
        indexes = [
            models.Index(fields=['member', 'check_in']),
            models.Index(fields=['member', 'date']),
            models.Index(fields=['date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['member'],
                condition=models.Q(check_out__isnull=True),
                name='unique_open_attendance_per_member',
            ),
        ]
    
    def __str__(self):
        return f"{self.member.user.full_name} - {self.check_in.strftime('%Y-%m-%d %H:%M')}"
    
    def duration(self):
        """Calculate duration of gym visit."""
        if self.check_out:
            delta = self.check_out - self.check_in
            hours = delta.total_seconds() / 3600
            return round(hours, 2)
        return None
    
    def is_checked_out(self):
        """Check if member has checked out."""
        return self.check_out is not None
    
    def checkout(self):
        """Mark member as checked out."""
        if not self.check_out:
            self.check_out = timezone.now()
            self.save()


class CheckInSession(models.Model):
    """Short-lived QR token used to authorize self check-in and check-out."""

    ACTION_CHECKIN = 'checkin'
    ACTION_CHECKOUT = 'checkout'
    ACTION_CHOICES = [
        (ACTION_CHECKIN, 'Check In'),
        (ACTION_CHECKOUT, 'Check Out'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name='checkin_sessions'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'checkin_sessions'
        verbose_name = 'Check-In Session'
        verbose_name_plural = 'Check-In Sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['member', 'action', 'used']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['used']),
        ]

    def __str__(self):
        return f"{self.member.user.full_name} - {self.action} ({'used' if self.used else 'open'})"

    def is_expired(self):
        """Check if the session token has expired."""
        return self.expires_at <= timezone.now()

    def mark_used(self):
        """Mark the session token as consumed."""
        if not self.used:
            self.used = True
            self.save(update_fields=['used'])


class Notification(models.Model):
    """Notification system for subscription expiry alerts and general notifications."""
    
    NOTIFICATION_TYPE_CHOICES = [
        ('expiry_7_days', 'Subscription Expires in 7 Days'),
        ('expiry_3_days', 'Subscription Expires in 3 Days'),
        ('expiry_1_day', 'Subscription Expires Tomorrow'),
        ('expired', 'Subscription Expired'),
        ('payment_received', 'Payment Received'),
        ('payment_failed', 'Payment Failed'),
        ('subscription_activated', 'Subscription Activated'),
        ('subscription_cancelled', 'Subscription Cancelled'),
        ('general', 'General Notification'),
    ]
    
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('dashboard', 'Dashboard'),
        ('both', 'Email & Dashboard'),
    ]
    
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    subscription = models.ForeignKey(
        'Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES
    )
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default='dashboard'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Tracking
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['member', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['member', 'subscription', 'notification_type']),
        ]
    
    def __str__(self):
        return f"{self.member.user.full_name} - {self.get_notification_type_display()}"
    
    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def mark_email_sent(self):
        """Mark email as sent."""
        if not self.email_sent:
            self.email_sent = True
            self.email_sent_at = timezone.now()
            self.save(update_fields=['email_sent', 'email_sent_at'])
