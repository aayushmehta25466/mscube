from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
from datetime import date, datetime, timedelta
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
        on_delete=models.CASCADE,
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
        return self.status == 'active' and self.end_date >= date.today()
    
    def days_remaining(self):
        """Calculate days remaining in subscription."""
        if self.end_date >= date.today():
            return (self.end_date - date.today()).days
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
        if self.status == 'active' and self.end_date < date.today():
            self.status = 'expired'
            self.save()


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
        on_delete=models.CASCADE,
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
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
        
        # Activate the subscription if payment is completed
        if self.subscription.status == 'pending':
            self.subscription.activate()
    
    def mark_failed(self, reason=''):
        """Mark payment as failed."""
        self.status = 'failed'
        if reason:
            self.notes = f"{self.notes}\nFailure reason: {reason}".strip()
        self.save()
    
    def save(self, *args, **kwargs):
        # Auto-generate transaction ID if not set
        if not self.transaction_id:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.transaction_id = f"TXN{timestamp}{self.subscription.member.id}"
        super().save(*args, **kwargs)


class Attendance(models.Model):
    """Attendance tracking for gym members."""
    
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
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
