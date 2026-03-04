"""
Business logic services for gym management operations.
Keeps complex logic out of views and ensures proper transaction handling.
"""
from django.db import transaction, IntegrityError
from django.utils import timezone
from datetime import timedelta
from .models import Subscription, Payment, Attendance
from accounts.models import Member


class SubscriptionService:
    """Service for handling subscription operations."""
    
    @staticmethod
    @transaction.atomic
    def create_subscription_with_payment(member, plan, payment_method='cash', start_date=None):
        """
        Create a subscription and payment in a single transaction.
        
        Args:
            member: Member instance
            plan: MembershipPlan instance
            payment_method: Payment method (cash, card, online, esewa)
            start_date: Subscription start date (defaults to today)
        
        Returns:
            tuple: (subscription, payment) instances
        
        Raises:
            ValueError: If member already has an active subscription
        """
        # Lock member row to prevent concurrent active subscription writes
        locked_member = Member.objects.select_for_update().get(pk=member.pk)

        if locked_member.subscriptions.filter(status='active').exists():
            raise ValueError(f'{member.user.full_name} already has an active subscription.')
        
        # Default start date to today
        if start_date is None:
            start_date = timezone.localdate()
        
        # Calculate end date
        end_date = start_date + timedelta(days=plan.duration_days)
        
        # Create subscription
        try:
            subscription = Subscription.objects.create(
                member=locked_member,
                plan=plan,
                start_date=start_date,
                end_date=end_date,
                status='pending'
            )
        except IntegrityError as exc:
            raise ValueError(f'{member.user.full_name} already has an active subscription.') from exc
        
        # Create payment
        payment = Payment.objects.create(
            subscription=subscription,
            amount=plan.price,
            payment_method=payment_method,
            status='pending'
        )
        
        # For cash/card, complete immediately
        if payment_method in ['cash', 'card']:
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.save(update_fields=['status', 'completed_at'])
            
            # Activate subscription
            subscription.status = 'active'
            subscription.save(update_fields=['status'])
        
        return subscription, payment
    
    @staticmethod
    @transaction.atomic
    def renew_subscription(member, plan, payment_method='cash'):
        """
        Renew or create a new subscription for a member.
        
        Args:
            member: Member instance
            plan: MembershipPlan instance
            payment_method: Payment method
        
        Returns:
            tuple: (subscription, payment) instances
        """
        locked_member = Member.objects.select_for_update().get(pk=member.pk)

        current_sub = locked_member.subscriptions.select_for_update().filter(status='active').first()
        
        if current_sub:
            # Cancel current subscription
            current_sub.status = 'cancelled'
            current_sub.save(update_fields=['status'])
        
        # Create new subscription
        return SubscriptionService.create_subscription_with_payment(
            locked_member, plan, payment_method
        )
    
    @staticmethod
    def check_and_expire_subscriptions():
        """
        Background task to check and expire subscriptions.
        Should be run daily via cron/celery.
        
        Returns:
            int: Number of subscriptions expired
        """
        today = timezone.localdate()
        expired_count = Subscription.objects.filter(
            status='active',
            end_date__lt=today
        ).update(status='expired')
        
        return expired_count


class AttendanceService:
    """Service for handling attendance operations."""
    
    @staticmethod
    def check_in_member(member):
        """
        Check in a member with full validation.
        
        Args:
            member: Member instance
        
        Returns:
            Attendance instance
        
        Raises:
            ValueError: If validation fails
        """
        active_sub = member.subscriptions.filter(status='active').first()
        
        if not active_sub:
            raise ValueError(
                f'{member.user.full_name} does not have an active subscription. '
                'Please renew membership before check-in.'
            )
        
        # Check subscription expiry
        today = timezone.localdate()
        if active_sub.end_date < today:
            # Auto-expire
            active_sub.status = 'expired'
            active_sub.save(update_fields=['status'])
            raise ValueError(
                f'{member.user.full_name}\'s subscription expired on {active_sub.end_date}. '
                'Please renew before check-in.'
            )

        with transaction.atomic():
            locked_member = Member.objects.select_for_update().get(pk=member.pk)
            existing = Attendance.objects.select_for_update().filter(
                member=locked_member,
                check_out__isnull=True,
            ).first()

            if existing:
                raise ValueError(
                    f'{locked_member.user.full_name} is already checked in at '
                    f'{existing.check_in.strftime("%I:%M %p")}. '
                    'Please check them out first.'
                )

            try:
                return Attendance.objects.create(member=locked_member)
            except IntegrityError as exc:
                raise ValueError(
                    f'{locked_member.user.full_name} already has an open attendance session. '
                    'Please complete checkout before a new check-in.'
                ) from exc
    
    @staticmethod
    def check_out_member(attendance):
        """
        Check out a member.
        
        Args:
            attendance: Attendance instance
        
        Returns:
            Attendance instance
        
        Raises:
            ValueError: If already checked out
        """
        if attendance.check_out:
            raise ValueError(
                f'{attendance.member.user.full_name} was already checked out at '
                f'{attendance.check_out.strftime("%I:%M %p")}.'
            )
        
        attendance.checkout()
        return attendance


class PaymentService:
    """Service for handling payment operations."""
    
    @staticmethod
    def validate_payment_amount(payment):
        """
        Validate payment amount matches subscription plan price.
        
        SECURITY: Prevents payment amount tampering attacks.
        
        Args:
            payment: Payment instance
        
        Raises:
            ValueError: If payment amount doesn't match plan price
        """
        expected_amount = payment.subscription.plan.price
        if payment.amount != expected_amount:
            raise ValueError(
                f'Payment amount does not match subscription plan price. '
                f'Expected: {expected_amount}, Got: {payment.amount}'
            )
    
    @staticmethod
    @transaction.atomic
    def complete_payment(payment):
        """
        Mark payment as completed and activate associated subscription.
        
        Args:
            payment: Payment instance
        
        Returns:
            Payment instance
        """
        locked_payment = Payment.objects.select_for_update().select_related('subscription').get(pk=payment.pk)

        # SECURITY: Validate payment amount before completion
        PaymentService.validate_payment_amount(locked_payment)

        # Idempotency guard for callback replays/double-processing
        if locked_payment.status == 'completed':
            return locked_payment

        locked_payment.status = 'completed'
        locked_payment.completed_at = timezone.now()
        locked_payment.save(update_fields=['status', 'completed_at'])
        
        # Activate subscription if pending
        subscription = Subscription.objects.select_for_update().get(pk=locked_payment.subscription.pk)
        if subscription.status == 'pending':
            subscription.status = 'active'
            subscription.save(update_fields=['status'])
        
        return locked_payment
    
    @staticmethod
    @transaction.atomic
    def refund_payment(payment, reason=''):
        """
        Process a refund for a payment.
        
        Args:
            payment: Payment instance
            reason: Refund reason
        
        Returns:
            Payment instance
        """
        locked_payment = Payment.objects.select_for_update().select_related('subscription').get(pk=payment.pk)

        if locked_payment.status != 'completed':
            raise ValueError('Only completed payments can be refunded.')
        
        locked_payment.status = 'refunded'
        if reason:
            locked_payment.notes = f"{locked_payment.notes}\nRefund reason: {reason}".strip()
        locked_payment.save(update_fields=['status', 'notes'])
        
        # Optionally cancel associated subscription
        subscription = Subscription.objects.select_for_update().get(pk=locked_payment.subscription.pk)
        if subscription.status == 'active':
            subscription.status = 'cancelled'
            subscription.save(update_fields=['status'])
        
        return locked_payment
