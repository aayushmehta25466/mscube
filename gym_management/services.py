"""
Business logic services for gym management operations.
Keeps complex logic out of views and ensures proper transaction handling.

Phase 2 Features:
- Enhanced Subscription Management (create, renew, cancel, upgrade)
- Expiry Notification System (7, 3, 1 day alerts)
- Payment System with eSewa integration
- Analytics and Reporting
- Export System (CSV, PDF, Excel)
"""
import csv
import hashlib
import hmac
import io
import logging
from decimal import Decimal
from datetime import timedelta
from typing import Optional, Tuple, List, Dict, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.db.models import Sum, Count, Avg, Q, F
from django.db.models.functions import TruncDate, TruncMonth, TruncHour, ExtractHour
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import Member
from .utils.location import calculate_distance_meters

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('security.audit')


class SubscriptionService:
    """Service for handling subscription operations with atomic transactions."""

    ACTIVE_SUBSCRIPTION_ERROR = 'Member already has an active subscription.'

    @staticmethod
    def calculate_subscription_period(plan, start_date=None):
        """Calculate the subscription start and end dates from plan duration."""
        if start_date is None:
            start_date = timezone.localdate()
        return start_date, start_date + timedelta(days=plan.duration_days)

    @staticmethod
    def validate_new_subscription(member, exclude_subscription_id=None):
        """Prevent more than one active subscription for the same member."""
        active_subscriptions = member.subscriptions.filter(status='active')
        if exclude_subscription_id:
            active_subscriptions = active_subscriptions.exclude(pk=exclude_subscription_id)

        if active_subscriptions.exists():
            raise ValidationError(SubscriptionService.ACTIVE_SUBSCRIPTION_ERROR)

    @staticmethod
    @transaction.atomic
    def create_subscription(member, plan, start_date=None):
        """Create a pending subscription after enforcing member eligibility rules."""
        from .models import Subscription

        if not member.is_active:
            raise ValidationError('Member account is inactive.')

        locked_member = Member.objects.select_for_update().get(pk=member.pk)
        SubscriptionService.validate_new_subscription(locked_member)

        start_date, end_date = SubscriptionService.calculate_subscription_period(plan, start_date)

        try:
            return Subscription.objects.create(
                member=locked_member,
                plan=plan,
                start_date=start_date,
                end_date=end_date,
                status='pending'
            )
        except IntegrityError as exc:
            raise ValidationError(SubscriptionService.ACTIVE_SUBSCRIPTION_ERROR) from exc

    @staticmethod
    @transaction.atomic
    def update_subscription(subscription, plan, start_date):
        """Update an existing subscription or create a replacement when the plan changes."""
        from .models import Subscription

        locked_subscription = Subscription.objects.select_for_update().select_related(
            'member__user',
            'plan',
        ).get(pk=subscription.pk)

        start_date, end_date = SubscriptionService.calculate_subscription_period(plan, start_date)

        if locked_subscription.plan_id != plan.pk:
            if locked_subscription.status != 'cancelled':
                locked_subscription.status = 'cancelled'
                locked_subscription.save(update_fields=['status', 'updated_at'])

            new_subscription = SubscriptionService.create_subscription(
                member=locked_subscription.member,
                plan=plan,
                start_date=start_date,
            )
            return new_subscription, True

        locked_subscription.plan = plan
        locked_subscription.start_date = start_date
        locked_subscription.end_date = end_date
        locked_subscription.save(update_fields=['plan', 'start_date', 'end_date', 'updated_at'])
        return locked_subscription, False
    
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
            ValidationError: If member already has an active subscription or is inactive
        """
        from .models import Payment
        
        subscription = SubscriptionService.create_subscription(
            member=member,
            plan=plan,
            start_date=start_date,
        )
        payment = PaymentService.create_payment(
            subscription=subscription,
            payment_method=payment_method,
        )
        
        # For cash/card, complete immediately
        if payment_method in ['cash', 'card']:
            payment, _ = PaymentService.complete_payment(payment)

        subscription.refresh_from_db()
        payment.refresh_from_db()
        
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
    @transaction.atomic
    def upgrade_subscription(member, new_plan, payment_method='cash', prorate: bool = True):
        """
        Upgrade a member's subscription to a new plan.
        
        The upgrade can optionally prorate the cost based on remaining days.
        
        Args:
            member: Member instance
            new_plan: MembershipPlan instance to upgrade to
            payment_method: Payment method for the upgrade
            prorate: If True, calculates prorated cost based on remaining days
        
        Returns:
            tuple: (new_subscription, payment, credit_applied)
        
        Raises:
            ValueError: If no active subscription or plan is same/lower
        """
        from .models import Subscription, Payment
        
        locked_member = Member.objects.select_for_update().get(pk=member.pk)
        
        current_sub = locked_member.subscriptions.select_for_update().filter(
            status='active'
        ).select_related('plan').first()
        
        if not current_sub:
            raise ValueError(f'{member.user.full_name} does not have an active subscription to upgrade.')
        
        # Validate upgrade (new plan should be higher priced)
        if new_plan.price <= current_sub.plan.price:
            raise ValueError(
                f'Upgrade plan must be higher priced than current plan. '
                f'Current: NPR {current_sub.plan.price}, New: NPR {new_plan.price}'
            )
        
        today = timezone.localdate()
        credit_applied = Decimal('0')
        
        if prorate and current_sub.end_date > today:
            # Calculate prorated credit from remaining days
            remaining_days = (current_sub.end_date - today).days
            daily_rate = current_sub.plan.price / current_sub.plan.duration_days
            credit_applied = daily_rate * remaining_days
        
        # Calculate upgrade cost
        upgrade_cost = new_plan.price - credit_applied
        if upgrade_cost < Decimal('0'):
            upgrade_cost = Decimal('0')
        
        # Expire current subscription
        current_sub.status = 'expired'
        current_sub.save(update_fields=['status'])
        
        # Create new subscription starting today
        end_date = today + timedelta(days=new_plan.duration_days)
        
        new_subscription = Subscription.objects.create(
            member=locked_member,
            plan=new_plan,
            start_date=today,
            end_date=end_date,
            status='pending'
        )
        
        # Create payment for upgrade cost
        payment = Payment.objects.create(
            subscription=new_subscription,
            amount=upgrade_cost,
            payment_method=payment_method,
            status='pending',
            notes=f'Upgrade from {current_sub.plan.name}. Credit applied: NPR {credit_applied:.2f}'
        )
        
        # For cash/card, complete immediately
        if payment_method in ['cash', 'card']:
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.save(update_fields=['status', 'completed_at'])
            
            new_subscription.status = 'active'
            new_subscription.save(update_fields=['status'])
        
        audit_logger.info(
            'SUBSCRIPTION_UPGRADE | member_id=%s | old_plan=%s | new_plan=%s | credit=%s | cost=%s',
            member.pk, current_sub.plan.name, new_plan.name, credit_applied, upgrade_cost
        )
        
        return new_subscription, payment, credit_applied
    
    @staticmethod
    @transaction.atomic
    def cancel_subscription(subscription, reason: str = '', refund: bool = False):
        """
        Cancel a subscription.
        
        Args:
            subscription: Subscription instance to cancel
            reason: Cancellation reason
            refund: If True, processes refund for completed payments
        
        Returns:
            tuple: (subscription, refund_amount)
        
        Raises:
            ValueError: If subscription is not active
        """
        from .models import Subscription, Payment
        
        locked_sub = Subscription.objects.select_for_update().get(pk=subscription.pk)
        
        if locked_sub.status not in ['active', 'pending']:
            raise ValueError(f'Cannot cancel subscription with status: {locked_sub.status}')
        
        refund_amount = Decimal('0')
        
        if refund and locked_sub.status == 'active':
            # Calculate prorated refund
            today = timezone.localdate()
            if locked_sub.end_date > today:
                remaining_days = (locked_sub.end_date - today).days
                total_days = locked_sub.plan.duration_days
                refund_amount = (locked_sub.plan.price * remaining_days) / total_days
        
        # Update subscription status
        locked_sub.status = 'cancelled'
        locked_sub.save(update_fields=['status'])
        
        # If refund requested, mark payments
        if refund and refund_amount > 0:
            completed_payment = locked_sub.payments.filter(status='completed').first()
            if completed_payment:
                PaymentService.refund_payment(
                    completed_payment,
                    reason=f'Subscription cancellation. {reason}'.strip()
                )
        
        audit_logger.info(
            'SUBSCRIPTION_CANCEL | subscription_id=%s | member_id=%s | refund=%s | reason=%s',
            locked_sub.pk, locked_sub.member.pk, refund_amount, reason
        )
        
        return locked_sub, refund_amount
    
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

    INVALID_QR_MESSAGE = 'This QR session is invalid. Please scan the QR code again.'
    EXPIRED_QR_MESSAGE = 'This QR session has expired. Please scan the QR code again.'
    LOCATION_REQUIRED_MESSAGE = 'Location access is required to continue.'
    INVALID_LOCATION_MESSAGE = 'Location data was invalid. Please try again.'

    @staticmethod
    def create_qr_session(member, action):
        """Create a short-lived QR session token for a member action."""
        from .models import CheckInSession

        if action not in {CheckInSession.ACTION_CHECKIN, CheckInSession.ACTION_CHECKOUT}:
            raise ValueError('Unsupported QR action.')

        return CheckInSession.objects.create(
            member=member,
            action=action,
            expires_at=timezone.now() + timedelta(seconds=settings.GYM_QR_SESSION_TTL_SECONDS),
        )

    @staticmethod
    def validate_qr_session(token, user, action):
        """Validate token existence, expiry, member ownership, and action."""
        from .models import CheckInSession

        try:
            session = CheckInSession.objects.select_related('member__user').get(
                pk=token,
                action=action,
            )
        except (CheckInSession.DoesNotExist, ValidationError, ValueError, TypeError) as exc:
            raise ValueError(AttendanceService.INVALID_QR_MESSAGE) from exc

        if session.used:
            raise ValueError(AttendanceService.INVALID_QR_MESSAGE)

        if session.is_expired():
            raise ValueError(AttendanceService.EXPIRED_QR_MESSAGE)

        member = getattr(user, 'member', None)
        if member is None:
            raise ValueError('Only members can use QR attendance.')

        if session.member_id != member.pk:
            raise ValueError(AttendanceService.INVALID_QR_MESSAGE)

        return session, member

    @staticmethod
    def _validate_active_subscription(member):
        """Validate and return the active subscription for a member."""
        with transaction.atomic():
            active_sub = (
                member.subscriptions
                .select_for_update()
                .filter(status='active')
                .select_related('plan')
                .first()
            )

            if not active_sub:
                raise ValueError(
                    f'{member.user.full_name} does not have an active subscription. '
                    'Please renew membership before check-in.'
                )

            today = timezone.localdate()
            if active_sub.end_date < today:
                active_sub.status = 'expired'
                active_sub.save(update_fields=['status'])
                expired_error = ValueError(
                    f'{member.user.full_name}\'s subscription expired on {active_sub.end_date}. '
                    'Please renew before check-in.'
                )
            else:
                expired_error = None

        if expired_error is not None:
            raise expired_error

        return active_sub

    @staticmethod
    def _validate_geolocation(latitude, longitude, rejection_message):
        """Validate the user coordinates fall within the configured gym radius."""
        if latitude in {None, ''} or longitude in {None, ''}:
            raise ValueError(AttendanceService.LOCATION_REQUIRED_MESSAGE)

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError) as exc:
            raise ValueError(AttendanceService.INVALID_LOCATION_MESSAGE) from exc

        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError(AttendanceService.INVALID_LOCATION_MESSAGE)

        distance_meters = calculate_distance_meters(
            latitude,
            longitude,
            settings.GYM_LATITUDE,
            settings.GYM_LONGITUDE,
        )

        if distance_meters > settings.GYM_RADIUS_METERS:
            raise ValueError(rejection_message)

        return distance_meters

    @staticmethod
    def _create_attendance_record(member, session_token=None, session_action=None):
        """Create an attendance row under lock, optionally consuming a QR token."""
        from .models import Attendance, CheckInSession

        with transaction.atomic():
            if session_token is not None:
                try:
                    locked_session = CheckInSession.objects.select_for_update().get(
                        pk=session_token,
                        action=session_action,
                        member=member,
                    )
                except (CheckInSession.DoesNotExist, ValidationError, ValueError, TypeError) as exc:
                    raise ValueError(AttendanceService.INVALID_QR_MESSAGE) from exc

                if locked_session.used:
                    raise ValueError(AttendanceService.INVALID_QR_MESSAGE)

                if locked_session.is_expired():
                    raise ValueError(AttendanceService.EXPIRED_QR_MESSAGE)
            else:
                locked_session = None

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
                attendance = Attendance.objects.create(member=locked_member)
            except IntegrityError as exc:
                raise ValueError(
                    f'{locked_member.user.full_name} already has an open attendance session. '
                    'Please complete checkout before a new check-in.'
                ) from exc

            if locked_session is not None:
                locked_session.used = True
                locked_session.save(update_fields=['used'])

            return attendance

    @staticmethod
    def _checkout_attendance_record(member, session_token):
        """Check out an open attendance row under lock and consume a QR token."""
        from .models import Attendance, CheckInSession

        with transaction.atomic():
            try:
                locked_session = CheckInSession.objects.select_for_update().get(
                    pk=session_token,
                    action=CheckInSession.ACTION_CHECKOUT,
                    member=member,
                )
            except (CheckInSession.DoesNotExist, ValidationError, ValueError, TypeError) as exc:
                raise ValueError(AttendanceService.INVALID_QR_MESSAGE) from exc

            if locked_session.used:
                raise ValueError(AttendanceService.INVALID_QR_MESSAGE)

            if locked_session.is_expired():
                raise ValueError(AttendanceService.EXPIRED_QR_MESSAGE)

            attendance = Attendance.objects.select_for_update().select_related('member__user').filter(
                member=member,
                check_out__isnull=True,
            ).first()

            if not attendance:
                raise ValueError('You do not have an active check-in session to check out from.')

            attendance.checkout()
            locked_session.used = True
            locked_session.save(update_fields=['used'])
            return attendance

    @staticmethod
    def process_self_check_in(user, token, latitude, longitude):
        """Process a tokenized, geofenced self check-in request."""
        session, member = AttendanceService.validate_qr_session(token, user, 'checkin')
        active_sub = AttendanceService._validate_active_subscription(member)
        distance_meters = AttendanceService._validate_geolocation(
            latitude,
            longitude,
            'You must be physically near the gym to check in.',
        )
        attendance = AttendanceService._create_attendance_record(
            member,
            session_token=session.pk,
            session_action=session.action,
        )
        return attendance, active_sub, distance_meters

    @staticmethod
    def process_self_check_out(user, token, latitude, longitude):
        """Process a tokenized, geofenced self check-out request."""
        session, member = AttendanceService.validate_qr_session(token, user, 'checkout')
        AttendanceService._validate_active_subscription(member)
        distance_meters = AttendanceService._validate_geolocation(
            latitude,
            longitude,
            'You must be physically near the gym to check out.',
        )
        attendance = AttendanceService._checkout_attendance_record(member, session.pk)
        return attendance, distance_meters
    
    @staticmethod
    def check_in_member(member):
        """
        Check in a member with full validation under a DB-level lock.

        Architecture note on transaction boundaries:
        - Subscription validation and expiry are handled in Phase 1: a dedicated
          atomic block that commits (or rolls back) independently.  This ensures
          that the expiry status change persists even though we subsequently raise
          a ValueError to abort the check-in.
        - Phase 2 wraps only the duplicate-check + attendance creation in its own
          atomic block with select_for_update(), which closes the TOCTOU race
          window where two concurrent check-in requests could both pass the
          "already checked-in?" guard and produce a duplicate record.  The
          partial-index DB constraint (unique_open_attendance_per_member) acts as
          a final backstop.

        Args:
            member: Member instance

        Returns:
            Attendance instance

        Raises:
            ValueError: If any validation fails
        """
        AttendanceService._validate_active_subscription(member)
        return AttendanceService._create_attendance_record(member)
    
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

    PENDING_SUBSCRIPTION_ERROR = 'Payment allowed only for pending subscriptions.'
    DUPLICATE_PAYMENT_ERROR = 'Payment already recorded for this subscription.'

    @staticmethod
    def validate_payment_creation(subscription, exclude_payment_id=None):
        """Ensure only one payment can be created and only for pending subscriptions."""
        if subscription.status != 'pending':
            raise ValidationError(PaymentService.PENDING_SUBSCRIPTION_ERROR)

        existing_payments = subscription.payments.all()
        if exclude_payment_id:
            existing_payments = existing_payments.exclude(pk=exclude_payment_id)

        if existing_payments.exists():
            raise ValidationError(PaymentService.DUPLICATE_PAYMENT_ERROR)

    @staticmethod
    @transaction.atomic
    def create_payment(subscription, payment_method, amount=None, notes=''):
        """Create a single pending payment for a pending subscription."""
        from .models import Payment, Subscription

        locked_subscription = Subscription.objects.select_for_update().select_related(
            'member__user',
            'plan',
        ).get(pk=subscription.pk)
        PaymentService.validate_payment_creation(locked_subscription)

        if amount is None:
            amount = locked_subscription.plan.price

        return Payment.objects.create(
            subscription=locked_subscription,
            amount=amount,
            payment_method=payment_method,
            status='pending',
            notes=notes,
        )
    
    @staticmethod
    def validate_payment_amount(payment):
        """
        Validate payment amount matches expected amount.
        
        SECURITY: Prevents payment amount tampering attacks.
        
        For regular subscriptions: amount must match plan price
        For upgrades: amount must be the prorated upgrade cost (plan price - credit)
        
        Args:
            payment: Payment instance
        
        Raises:
            ValueError: If payment amount doesn't match expected amount
        """
        # Check if this is an upgrade payment
        is_upgrade = 'upgrade' in payment.notes.lower() if payment.notes else False
        
        if is_upgrade:
            # For upgrades, payment.amount is already the calculated upgrade cost
            # We validate that the amount is positive and less than or equal to plan price
            expected_max = payment.subscription.plan.price
            if payment.amount < Decimal('0'):
                raise ValueError(f'Upgrade payment amount cannot be negative: {payment.amount}')
            if payment.amount > expected_max:
                raise ValueError(
                    f'Upgrade payment amount exceeds plan price. '
                    f'Maximum: {expected_max}, Got: {payment.amount}'
                )
        else:
            # For regular subscriptions, amount must exactly match plan price
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
        Mark payment as completed and activate the associated subscription.

        If another active subscription exists for the same member it is
        transitioned to 'expired' before the new one is activated.  This
        prevents the unique-active-subscription constraint from being
        violated when a member pays for a renewal against a subscription
        that is still technically pending while a previous one is still
        active.

        Args:
            payment: Payment instance

        Returns:
            tuple: (payment, expired_count)
                payment       – the updated Payment instance
                expired_count – number of previously-active subscriptions
                                that were expired (0 or 1 in normal flow)
        """
        from .models import Payment, Subscription
        
        locked_payment = Payment.objects.select_for_update().select_related(
            'subscription__member',
            'subscription__plan',
        ).get(pk=payment.pk)

        # SECURITY: Validate payment amount before completion
        PaymentService.validate_payment_amount(locked_payment)

        if locked_payment.status not in {'pending', 'completed'}:
            raise ValueError(f'Cannot complete payment with status: {locked_payment.status}')

        payment_was_already_completed = locked_payment.status == 'completed'

        if not payment_was_already_completed:
            locked_payment.status = 'completed'
            locked_payment.completed_at = timezone.now()
            locked_payment.save(update_fields=['status', 'completed_at'])

        # Activate subscription if pending, expiring any other active ones first.
        subscription = Subscription.objects.select_for_update().select_related('plan').get(
            pk=locked_payment.subscription.pk
        )
        expired_count = 0
        if subscription.status == 'pending':
            # Expire any other active subscription for this member before activating
            # the new one (handles renewal-while-still-active scenario).
            expired_count = Subscription.objects.filter(
                member=subscription.member,
                status='active',
            ).exclude(pk=subscription.pk).update(status='expired')

            start_date, end_date = SubscriptionService.calculate_subscription_period(subscription.plan)
            subscription.status = 'active'
            subscription.start_date = start_date
            subscription.end_date = end_date
            subscription.save(update_fields=['status', 'start_date', 'end_date'])
        elif subscription.status != 'active':
            raise ValidationError(PaymentService.PENDING_SUBSCRIPTION_ERROR)

        return locked_payment, expired_count
    
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
        from .models import Payment, Subscription
        
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


class NotificationService:
    """Service for handling expiry notifications and alerts."""
    
    EXPIRY_ALERT_DAYS = [7, 3, 1]  # Days before expiry to send alerts
    
    @staticmethod
    def get_expiring_subscriptions(days_before: int) -> List:
        """
        Get subscriptions expiring in exactly N days.
        
        Args:
            days_before: Days until expiry
            
        Returns:
            QuerySet of Subscription objects
        """
        from .models import Subscription
        
        target_date = timezone.localdate() + timedelta(days=days_before)
        return Subscription.objects.filter(
            status='active',
            end_date=target_date
        ).select_related('member__user', 'plan')
    
    @staticmethod
    def get_notification_type(days_before: int) -> str:
        """Map days to notification type."""
        mapping = {
            7: 'expiry_7_days',
            3: 'expiry_3_days',
            1: 'expiry_1_day',
            0: 'expired',
        }
        return mapping.get(days_before, 'general')
    
    @staticmethod
    def notification_already_sent(member, subscription, notification_type: str) -> bool:
        """Check if notification was already sent for this subscription/type combo."""
        from .models import Notification
        
        return Notification.objects.filter(
            member=member,
            subscription=subscription,
            notification_type=notification_type
        ).exists()
    
    @staticmethod
    @transaction.atomic
    def create_expiry_notification(subscription, days_before: int, channel: str = 'both'):
        """
        Create an expiry notification for a subscription.
        
        Args:
            subscription: Subscription instance
            days_before: Days until expiry
            channel: Notification channel (email, dashboard, both)
            
        Returns:
            Notification instance or None if already sent
        """
        from .models import Notification
        
        notification_type = NotificationService.get_notification_type(days_before)
        
        # Prevent duplicate notifications
        if NotificationService.notification_already_sent(
            subscription.member, subscription, notification_type
        ):
            logger.info(f"Notification {notification_type} already sent to {subscription.member.user.email}")
            return None
        
        # Build notification content
        if days_before == 0:
            title = "Your Subscription Has Expired"
            message = (
                f"Your {subscription.plan.name} subscription has expired. "
                f"Please renew to continue enjoying our facilities."
            )
        else:
            day_word = "day" if days_before == 1 else "days"
            title = f"Subscription Expiring in {days_before} {day_word}"
            message = (
                f"Your {subscription.plan.name} subscription will expire on {subscription.end_date}. "
                f"Renew now to avoid interruption to your gym access."
            )
        
        notification = Notification.objects.create(
            member=subscription.member,
            subscription=subscription,
            notification_type=notification_type,
            channel=channel,
            title=title,
            message=message
        )
        
        logger.info(f"Created {notification_type} notification for {subscription.member.user.email}")
        return notification
    
    @staticmethod
    def send_email_notification(notification) -> bool:
        """
        Send email notification.
        
        Args:
            notification: Notification instance
            
        Returns:
            bool: True if email sent successfully
        """
        if notification.email_sent:
            return True
        
        try:
            member = notification.member
            context = {
                'member_name': member.user.full_name,
                'notification': notification,
                'subscription': notification.subscription,
            }
            
            # Render email template
            html_message = render_to_string('gym_management/emails/notification.html', context)
            plain_message = f"{notification.title}\n\n{notification.message}"
            
            send_mail(
                subject=notification.title,
                message=plain_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@mscube.com'),
                recipient_list=[member.user.email],
                html_message=html_message,
                fail_silently=False,
            )
            
            notification.mark_email_sent()
            logger.info(f"Email sent to {member.user.email} for {notification.notification_type}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {notification.member.user.email}: {e}")
            return False
    
    @staticmethod
    def process_expiry_notifications():
        """
        Background task to process all expiry notifications.
        Should be run daily via cron/celery.
        
        Returns:
            dict: Statistics of notifications processed
        """
        from .models import Notification
        
        stats = {
            'notifications_created': 0,
            'emails_sent': 0,
            'errors': 0,
        }
        
        # Prefetch all existing notifications to avoid N+1 queries
        all_notification_keys = set()
        for days in NotificationService.EXPIRY_ALERT_DAYS:
            subscriptions = NotificationService.get_expiring_subscriptions(days)
            subscription_ids = list(subscriptions.values_list('id', flat=True))
            
            if subscription_ids:
                notification_type = NotificationService.get_notification_type(days)
                
                # Fetch existing notifications in bulk
                existing_notifications = Notification.objects.filter(
                    subscription_id__in=subscription_ids,
                    notification_type=notification_type
                ).values_list('member_id', 'subscription_id', 'notification_type')
                
                # Build a set of (member_id, subscription_id, notification_type) tuples
                for notif in existing_notifications:
                    all_notification_keys.add(notif)
        
        # Process each alert window
        for days in NotificationService.EXPIRY_ALERT_DAYS:
            subscriptions = NotificationService.get_expiring_subscriptions(days)
            notification_type = NotificationService.get_notification_type(days)
            
            for subscription in subscriptions:
                try:
                    # Check in-memory if notification already sent
                    key = (subscription.member_id, subscription.id, notification_type)
                    if key in all_notification_keys:
                        logger.info(f"Notification {notification_type} already sent to {subscription.member.user.email}")
                        continue
                    
                    # Create notification directly (skip duplicate check since we did it above)
                    if days == 0:
                        title = "Your Subscription Has Expired"
                        message = (
                            f"Your {subscription.plan.name} subscription has expired. "
                            f"Please renew to continue enjoying our facilities."
                        )
                    else:
                        day_word = "day" if days == 1 else "days"
                        title = f"Subscription Expiring in {days} {day_word}"
                        message = (
                            f"Your {subscription.plan.name} subscription will expire on {subscription.end_date}. "
                            f"Renew now to avoid interruption to your gym access."
                        )
                    
                    notification = Notification.objects.create(
                        member=subscription.member,
                        subscription=subscription,
                        notification_type=notification_type,
                        channel='both',
                        title=title,
                        message=message
                    )
                    
                    stats['notifications_created'] += 1
                    all_notification_keys.add(key)  # Add to set to prevent duplicates in same run
                    
                    # Send email if channel includes email
                    if notification.channel in ['email', 'both']:
                        if NotificationService.send_email_notification(notification):
                            stats['emails_sent'] += 1
                        else:
                            stats['errors'] += 1
                            
                except Exception as e:
                    logger.error(f"Error processing notification for {subscription}: {e}")
                    stats['errors'] += 1
        
        # Also process expired subscriptions (0 days)
        expired_subs = NotificationService.get_expiring_subscriptions(-1)  # Yesterday = expired
        expired_sub_ids = list(expired_subs.values_list('id', flat=True))
        
        if expired_sub_ids:
            # Fetch existing expired notifications in bulk
            existing_expired = Notification.objects.filter(
                subscription_id__in=expired_sub_ids,
                notification_type='expired'
            ).values_list('member_id', 'subscription_id', 'notification_type')
            
            for notif in existing_expired:
                all_notification_keys.add(notif)
        
        for subscription in expired_subs:
            try:
                # Update subscription status
                if subscription.status == 'active':
                    subscription.status = 'expired'
                    subscription.save(update_fields=['status'])
                
                # Check if notification already sent
                key = (subscription.member_id, subscription.id, 'expired')
                if key in all_notification_keys:
                    continue
                
                notification = Notification.objects.create(
                    member=subscription.member,
                    subscription=subscription,
                    notification_type='expired',
                    channel='both',
                    title="Your Subscription Has Expired",
                    message=(
                        f"Your {subscription.plan.name} subscription has expired. "
                        f"Please renew to continue enjoying our facilities."
                    )
                )
                
                stats['notifications_created'] += 1
                if NotificationService.send_email_notification(notification):
                    stats['emails_sent'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing expired notification for {subscription}: {e}")
                stats['errors'] += 1
        
        logger.info(f"Expiry notification processing complete: {stats}")
        return stats
    
    @staticmethod
    def get_unread_notifications(member, limit: int = 20):
        """Get unread dashboard notifications for a member."""
        from .models import Notification
        
        return Notification.objects.filter(
            member=member,
            is_read=False,
            channel__in=['dashboard', 'both']
        ).order_by('-created_at')[:limit]
    
    @staticmethod
    def mark_notifications_read(member, notification_ids: List[int] = None):
        """
        Mark notifications as read.
        
        Args:
            member: Member instance
            notification_ids: Optional list of notification IDs (marks all if None)
        """
        from .models import Notification
        
        queryset = Notification.objects.filter(member=member, is_read=False)
        
        if notification_ids:
            queryset = queryset.filter(pk__in=notification_ids)
        
        queryset.update(is_read=True, read_at=timezone.now())


class EsewaPaymentService:
    """Service for eSewa payment gateway integration."""
    
    # eSewa Configuration (should be in settings)
    ESEWA_MERCHANT_ID = getattr(settings, 'ESEWA_MERCHANT_ID', 'EPAYTEST')
    ESEWA_SECRET_KEY = getattr(settings, 'ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')
    ESEWA_BASE_URL = getattr(settings, 'ESEWA_BASE_URL', 'https://rc-epay.esewa.com.np')
    ESEWA_VERIFY_URL = f"{ESEWA_BASE_URL}/api/epay/transaction/status/"
    ESEWA_PAYMENT_URL = f"{ESEWA_BASE_URL}/api/epay/main/v2/form"
    
    @staticmethod
    def generate_signature(total_amount: Decimal, transaction_uuid: str, product_code: str) -> str:
        """
        Generate HMAC-SHA256 signature for eSewa payment.
        
        Args:
            total_amount: Total payment amount
            transaction_uuid: Unique transaction ID
            product_code: Product/Merchant code
            
        Returns:
            Base64 encoded signature
        """
        import base64
        
        # Format: total_amount,transaction_uuid,product_code
        message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
        
        signature = hmac.new(
            EsewaPaymentService.ESEWA_SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode()
    
    @staticmethod
    @transaction.atomic
    def initiate_payment(payment, success_url: str, failure_url: str) -> Dict[str, Any]:
        """
        Initiate eSewa payment.
        
        Args:
            payment: Payment instance
            success_url: URL for successful payment callback
            failure_url: URL for failed payment callback
            
        Returns:
            dict: Payment initiation data for frontend form
        """
        from .models import Payment
        
        locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
        
        if locked_payment.status != 'pending':
            raise ValueError('Payment is not in pending state.')
        
        if locked_payment.payment_method != 'esewa':
            raise ValueError('Payment method is not eSewa.')
        
        # Generate signature
        signature = EsewaPaymentService.generate_signature(
            locked_payment.amount,
            locked_payment.transaction_id,
            EsewaPaymentService.ESEWA_MERCHANT_ID
        )
        
        # Prepare form data for eSewa
        payment_data = {
            'amount': str(locked_payment.amount),
            'tax_amount': '0',
            'total_amount': str(locked_payment.amount),
            'transaction_uuid': locked_payment.transaction_id,
            'product_code': EsewaPaymentService.ESEWA_MERCHANT_ID,
            'product_service_charge': '0',
            'product_delivery_charge': '0',
            'success_url': success_url,
            'failure_url': failure_url,
            'signed_field_names': 'total_amount,transaction_uuid,product_code',
            'signature': signature,
        }
        
        audit_logger.info(
            'ESEWA_PAYMENT_INITIATE | payment_id=%s | transaction_id=%s | amount=%s',
            locked_payment.pk, locked_payment.transaction_id, locked_payment.amount
        )
        
        return {
            'payment_url': EsewaPaymentService.ESEWA_PAYMENT_URL,
            'form_data': payment_data,
            'payment': locked_payment,
        }
    
    @staticmethod
    def verify_signature(data: str, signature: str) -> bool:
        """
        Verify eSewa callback signature.
        
        Args:
            data: Signed data string
            signature: Provided signature
            
        Returns:
            bool: True if signature is valid
        """
        import base64
        
        expected_signature = hmac.new(
            EsewaPaymentService.ESEWA_SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).digest()
        
        return hmac.compare_digest(
            base64.b64encode(expected_signature).decode(),
            signature
        )
    
    @staticmethod
    @transaction.atomic
    def process_success_callback(
        transaction_uuid: str,
        esewa_transaction_code: str,
        esewa_ref_id: str,
        signature: str,
        total_amount: str
    ) -> Tuple[bool, str, Optional['Payment']]:
        """
        Process successful eSewa payment callback.
        
        Args:
            transaction_uuid: Our transaction ID
            esewa_transaction_code: eSewa's transaction code
            esewa_ref_id: eSewa's reference ID
            signature: Callback signature
            total_amount: Paid amount
            
        Returns:
            tuple: (success, message, payment)
        """
        from .models import Payment
        
        try:
            payment = Payment.objects.select_for_update().get(transaction_id=transaction_uuid)
        except Payment.DoesNotExist:
            audit_logger.warning(
                'ESEWA_CALLBACK_INVALID | transaction_uuid=%s | reason=payment_not_found',
                transaction_uuid
            )
            return False, 'Payment not found.', None
        
        # Idempotency: Already completed
        if payment.status == 'completed':
            audit_logger.info(
                'ESEWA_CALLBACK_REPLAY | payment_id=%s | transaction_id=%s',
                payment.pk, transaction_uuid
            )
            return True, 'Payment already processed.', payment
        
        # Verify callback signature
        signed_data = f"transaction_code={esewa_transaction_code},status=COMPLETE,total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={EsewaPaymentService.ESEWA_MERCHANT_ID},signed_field_names=transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names"
        
        if not EsewaPaymentService.verify_signature(signed_data, signature):
            audit_logger.warning(
                'ESEWA_CALLBACK_SIGNATURE_INVALID | payment_id=%s | transaction_id=%s',
                payment.pk, transaction_uuid
            )
            # Don't fail immediately - proceed to server-side verification
        
        # Verify with eSewa server
        is_verified = EsewaPaymentService.verify_transaction_with_esewa(
            transaction_uuid, Decimal(total_amount)
        )
        
        if not is_verified:
            audit_logger.error(
                'ESEWA_VERIFICATION_FAILED | payment_id=%s | transaction_id=%s',
                payment.pk, transaction_uuid
            )
            payment.status = 'failed'
            payment.notes = f"{payment.notes}\neSewa verification failed."
            payment.save(update_fields=['status', 'notes'])
            return False, 'Payment verification failed.', payment
        
        # Amount validation
        if Decimal(total_amount) != payment.amount:
            audit_logger.error(
                'ESEWA_AMOUNT_MISMATCH | payment_id=%s | expected=%s | received=%s',
                payment.pk, payment.amount, total_amount
            )
            payment.status = 'failed'
            payment.notes = f"{payment.notes}\nAmount mismatch: expected {payment.amount}, received {total_amount}."
            payment.save(update_fields=['status', 'notes'])
            return False, 'Payment amount mismatch.', payment
        
        # Update payment record
        payment.esewa_transaction_code = esewa_transaction_code
        payment.esewa_ref_id = esewa_ref_id
        payment.save(update_fields=['esewa_transaction_code', 'esewa_ref_id'])
        
        # Complete payment using PaymentService
        payment, expired_count = PaymentService.complete_payment(payment)
        
        audit_logger.info(
            'ESEWA_PAYMENT_SUCCESS | payment_id=%s | transaction_id=%s | esewa_code=%s',
            payment.pk, transaction_uuid, esewa_transaction_code
        )
        
        return True, 'Payment completed successfully.', payment
    
    @staticmethod
    @transaction.atomic
    def process_failure_callback(transaction_uuid: str, reason: str = '') -> Tuple[bool, str, Optional['Payment']]:
        """
        Process failed eSewa payment callback.
        
        Args:
            transaction_uuid: Our transaction ID
            reason: Failure reason
            
        Returns:
            tuple: (success, message, payment)
        """
        from .models import Payment
        
        try:
            payment = Payment.objects.select_for_update().get(transaction_id=transaction_uuid)
        except Payment.DoesNotExist:
            return False, 'Payment not found.', None
        
        if payment.status not in ['pending', 'failed']:
            return True, 'Payment already processed.', payment
        
        payment.status = 'failed'
        payment.notes = f"{payment.notes}\neSewa payment failed: {reason}".strip()
        payment.save(update_fields=['status', 'notes'])
        
        audit_logger.warning(
            'ESEWA_PAYMENT_FAILED | payment_id=%s | transaction_id=%s | reason=%s',
            payment.pk, transaction_uuid, reason
        )
        
        return True, 'Payment failure recorded.', payment
    
    @staticmethod
    def verify_transaction_with_esewa(transaction_uuid: str, total_amount: Decimal) -> bool:
        """
        Verify transaction with eSewa server.
        
        Args:
            transaction_uuid: Our transaction ID
            total_amount: Expected amount
            
        Returns:
            bool: True if verified
        """
        import requests
        
        try:
            response = requests.get(
                EsewaPaymentService.ESEWA_VERIFY_URL,
                params={
                    'product_code': EsewaPaymentService.ESEWA_MERCHANT_ID,
                    'transaction_uuid': transaction_uuid,
                    'total_amount': str(total_amount),
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('status') == 'COMPLETE'
            
            return False
            
        except Exception as e:
            logger.error(f"eSewa verification error: {e}")
            return False


class MemberService:
    """Service for member lifecycle management including deactivation."""
    
    @staticmethod
    @transaction.atomic
    def deactivate_member(member, reason: str = '') -> Member:
        """
        Deactivate a member account (soft delete).
        
        This prevents the member from:
        - Checking in for attendance
        - Creating new subscriptions
        - Making payments
        - Appearing in active member dashboards
        
        Args:
            member: Member instance to deactivate
            reason: Deactivation reason for audit trail
            
        Returns:
            Member: The deactivated member instance
            
        Raises:
            ValueError: If member is already inactive
        """
        # Use all_objects to access member regardless of active status
        locked_member = Member.all_objects.select_for_update().get(pk=member.pk)
        
        if not locked_member.is_active:
            raise ValueError(f'Member {member.user.full_name} is already inactive.')
        
        # Mark as inactive
        locked_member.is_active = False
        locked_member.deactivated_at = timezone.now()
        locked_member.save(update_fields=['is_active', 'deactivated_at'])
        
        # Cancel all active subscriptions
        active_subs = locked_member.subscriptions.filter(status='active')
        for subscription in active_subs:
            subscription.status = 'cancelled'
            subscription.save(update_fields=['status'])
        
        audit_logger.info(
            'MEMBER_DEACTIVATED | member_id=%s | user_email=%s | reason=%s',
            locked_member.pk, locked_member.user.email, reason
        )
        
        return locked_member
    
    @staticmethod
    @transaction.atomic
    def reactivate_member(member) -> Member:
        """
        Reactivate a deactivated member account.
        
        Args:
            member: Member instance to reactivate
            
        Returns:
            Member: The reactivated member instance
            
        Raises:
            ValueError: If member is already active
        """
        # Use all_objects to access inactive members
        from accounts.models import Member as MemberModel
        locked_member = MemberModel.all_objects.select_for_update().get(pk=member.pk)
        
        if locked_member.is_active:
            raise ValueError(f'Member {member.user.full_name} is already active.')
        
        # Mark as active
        locked_member.is_active = True
        locked_member.deactivated_at = None
        locked_member.save(update_fields=['is_active', 'deactivated_at'])
        
        audit_logger.info(
            'MEMBER_REACTIVATED | member_id=%s | user_email=%s',
            locked_member.pk, locked_member.user.email
        )
        
        return locked_member
    
    @staticmethod
    def can_member_check_in(member) -> Tuple[bool, str]:
        """
        Check if a member can check in for attendance.
        
        Args:
            member: Member instance
            
        Returns:
            tuple: (can_check_in, reason_if_not)
        """
        # Check if member is active
        if not member.is_active:
            return False, 'Member account is inactive.'
        
        # Check if member has active subscription
        has_active_sub = member.subscriptions.filter(status='active').exists()
        if not has_active_sub:
            return False, 'No active subscription.'
        
        # Check if member already has an open attendance
        from .models import Attendance
        has_open_attendance = Attendance.objects.filter(
            member=member,
            check_out__isnull=True
        ).exists()
        if has_open_attendance:
            return False, 'Already checked in.'
        
        return True, ''
    
    @staticmethod
    def can_member_subscribe(member) -> Tuple[bool, str]:
        """
        Check if a member can create a new subscription.
        
        Args:
            member: Member instance
            
        Returns:
            tuple: (can_subscribe, reason_if_not)
        """
        # Check if member is active
        if not member.is_active:
            return False, 'Member account is inactive.'
        
        # Check if member already has an active subscription
        has_active_sub = member.subscriptions.filter(status='active').exists()
        if has_active_sub:
            return False, 'already has an active subscription.'
        
        return True, ''


class AnalyticsService:
    """Service for generating analytics and reports."""
    
    @staticmethod
    def get_revenue_report(start_date=None, end_date=None) -> Dict[str, Any]:
        """
        Generate revenue report for the given date range.
        
        Args:
            start_date: Report start date (defaults to 30 days ago)
            end_date: Report end date (defaults to today)
            
        Returns:
            dict: Revenue statistics
        """
        from .models import Payment
        
        today = timezone.localdate()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = today - timedelta(days=30)
        
        # Base queryset
        payments = Payment.objects.filter(
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        )
        
        # Total revenue
        total_revenue = payments.aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # Revenue by payment method
        revenue_by_method = payments.values('payment_method').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')
        
        # Daily revenue trend
        daily_revenue = payments.annotate(
            date=TruncDate('completed_at')
        ).values('date').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('date')
        
        # Monthly revenue (for charts)
        monthly_revenue = payments.annotate(
            month=TruncMonth('completed_at')
        ).values('month').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('month')
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_revenue': total_revenue['total'] or Decimal('0'),
            'total_transactions': total_revenue['count'] or 0,
            'average_transaction': (
                (total_revenue['total'] or Decimal('0')) / total_revenue['count']
                if total_revenue['count'] else Decimal('0')
            ),
            'revenue_by_method': list(revenue_by_method),
            'daily_revenue': list(daily_revenue),
            'monthly_revenue': list(monthly_revenue),
        }
    
    @staticmethod
    def get_membership_analytics() -> Dict[str, Any]:
        """
        Generate membership analytics report.
        
        Returns:
            dict: Membership statistics
        """
        from .models import Subscription, MembershipPlan
        
        today = timezone.localdate()
        
        # Total members (all registered members for analytics)
        total_members = Member.all_objects.count()
        
        # Active subscriptions
        active_subscriptions = Subscription.objects.filter(status='active').count()
        
        # Subscription breakdown by status
        subscription_by_status = Subscription.objects.values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        # Subscription breakdown by plan
        subscription_by_plan = Subscription.objects.filter(
            status='active'
        ).values(
            'plan__name', 'plan__price'
        ).annotate(
            count=Count('id'),
            revenue=Sum('plan__price')
        ).order_by('-count')
        
        # Expiring soon (next 7 days)
        expiring_soon = Subscription.objects.filter(
            status='active',
            end_date__gte=today,
            end_date__lte=today + timedelta(days=7)
        ).count()
        
        # New subscriptions this month
        first_of_month = today.replace(day=1)
        new_this_month = Subscription.objects.filter(
            created_at__date__gte=first_of_month
        ).count()
        
        # Churn rate (expired/cancelled in last 30 days)
        thirty_days_ago = today - timedelta(days=30)
        churned = Subscription.objects.filter(
            updated_at__date__gte=thirty_days_ago,
            status__in=['expired', 'cancelled']
        ).count()
        
        active_30_days_ago = Subscription.objects.filter(
            created_at__date__lte=thirty_days_ago,
            status='active'
        ).count()
        
        churn_rate = (churned / active_30_days_ago * 100) if active_30_days_ago else 0
        
        # Members without subscription
        members_without_sub = Member.objects.filter(
            is_active=True
        ).exclude(
            subscriptions__status='active'
        ).count()
        
        return {
            'total_members': total_members,
            'active_subscriptions': active_subscriptions,
            'subscription_rate': (active_subscriptions / total_members * 100) if total_members else 0,
            'subscription_by_status': list(subscription_by_status),
            'subscription_by_plan': list(subscription_by_plan),
            'expiring_soon': expiring_soon,
            'new_this_month': new_this_month,
            'churn_rate': round(churn_rate, 2),
            'members_without_subscription': members_without_sub,
        }
    
    @staticmethod
    def get_attendance_analytics(start_date=None, end_date=None) -> Dict[str, Any]:
        """
        Generate attendance analytics report.
        
        Args:
            start_date: Report start date
            end_date: Report end date
            
        Returns:
            dict: Attendance statistics
        """
        from .models import Attendance
        
        today = timezone.localdate()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = today - timedelta(days=30)
        
        # Base queryset
        attendance = Attendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Total visits
        total_visits = attendance.count()
        
        # Unique visitors
        unique_visitors = attendance.values('member').distinct().count()
        
        # Average visits per day
        days_count = (end_date - start_date).days + 1
        avg_visits_per_day = total_visits / days_count if days_count else 0
        
        # Peak hours
        peak_hours = attendance.annotate(
            hour=ExtractHour('check_in')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        # Daily trend
        daily_attendance = attendance.values('date').annotate(
            count=Count('id'),
            unique_members=Count('member', distinct=True)
        ).order_by('date')
        
        # Average duration (for completed visits)
        completed_visits = attendance.filter(check_out__isnull=False)
        avg_duration = completed_visits.annotate(
            duration=F('check_out') - F('check_in')
        ).aggregate(avg=Avg('duration'))
        
        avg_duration_hours = (
            avg_duration['avg'].total_seconds() / 3600
            if avg_duration['avg'] else 0
        )
        
        # Top members by attendance
        top_members = attendance.values(
            'member__user__full_name', 'member__id'
        ).annotate(
            visit_count=Count('id')
        ).order_by('-visit_count')[:10]
        
        # Inactive members (no attendance in last 14 days)
        two_weeks_ago = today - timedelta(days=14)
        active_member_ids = Attendance.objects.filter(
            date__gte=two_weeks_ago
        ).values_list('member_id', flat=True)
        
        inactive_count = Member.objects.filter(
            is_active=True,
            subscriptions__status='active'
        ).exclude(id__in=active_member_ids).distinct().count()
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_visits': total_visits,
            'unique_visitors': unique_visitors,
            'avg_visits_per_day': round(avg_visits_per_day, 1),
            'peak_hours': list(peak_hours),
            'daily_attendance': list(daily_attendance),
            'avg_duration_hours': round(avg_duration_hours, 2),
            'top_members': list(top_members),
            'inactive_members_count': inactive_count,
        }
    
    @staticmethod
    def get_inactive_members(days: int = 14) -> List:
        """
        Get members with active subscriptions who haven't visited recently.
        
        Args:
            days: Number of days to consider as inactive
            
        Returns:
            QuerySet of Member objects
        """
        from .models import Attendance
        
        cutoff_date = timezone.localdate() - timedelta(days=days)
        
        # Members who visited within the period
        active_member_ids = Attendance.objects.filter(
            date__gte=cutoff_date
        ).values_list('member_id', flat=True)
        
        # Members with active subscriptions but no recent visits
        return Member.objects.filter(
            is_active=True,
            subscriptions__status='active'
        ).exclude(
            id__in=active_member_ids
        ).select_related('user').distinct()


class ExportService:
    """Service for exporting reports to various formats."""
    
    @staticmethod
    def export_to_csv(data: List[Dict], filename: str, fieldnames: List[str] = None) -> io.StringIO:
        """
        Export data to CSV format.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename (for headers)
            fieldnames: Optional list of field names (auto-detected if not provided)
            
        Returns:
            StringIO object with CSV content
        """
        output = io.StringIO()
        
        if not data:
            return output
        
        if not fieldnames:
            fieldnames = list(data[0].keys())
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        
        output.seek(0)
        return output
    
    @staticmethod
    def export_payments_csv(start_date=None, end_date=None) -> io.StringIO:
        """
        Export payment records to CSV.
        
        Args:
            start_date: Filter start date
            end_date: Filter end date
            
        Returns:
            StringIO object with CSV content
        """
        from .models import Payment
        
        today = timezone.localdate()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = today - timedelta(days=30)
        
        payments = Payment.objects.filter(
            initiated_at__date__gte=start_date,
            initiated_at__date__lte=end_date
        ).select_related(
            'subscription__member__user', 'subscription__plan'
        ).order_by('-initiated_at')
        
        data = []
        for payment in payments:
            data.append({
                'Transaction ID': payment.transaction_id,
                'Date': payment.initiated_at.strftime('%Y-%m-%d %H:%M'),
                'Member': payment.subscription.member.user.full_name,
                'Email': payment.subscription.member.user.email,
                'Plan': payment.subscription.plan.name,
                'Amount': str(payment.amount),
                'Method': payment.get_payment_method_display(),
                'Status': payment.get_status_display(),
                'Completed At': payment.completed_at.strftime('%Y-%m-%d %H:%M') if payment.completed_at else '',
            })
        
        return ExportService.export_to_csv(data, 'payments.csv')
    
    @staticmethod
    def export_members_csv(include_subscription: bool = True) -> io.StringIO:
        """
        Export member records to CSV.
        
        Args:
            include_subscription: Include current subscription info
            
        Returns:
            StringIO object with CSV content
        """
        from .models import Subscription
        
        # Export all members (including inactive) for administrative purposes
        members = Member.all_objects.select_related('user')
        
        if include_subscription:
            from django.db.models import Prefetch
            members = members.prefetch_related(
                Prefetch(
                    'subscriptions',
                    queryset=Subscription.objects.filter(status='active').select_related('plan'),
                    to_attr='active_subs'
                )
            )
        
        data = []
        for member in members:
            row = {
                'ID': member.id,
                'Full Name': member.user.full_name,
                'Email': member.user.email,
                'Phone': member.user.phone or '',
                'Date of Birth': str(member.date_of_birth) if member.date_of_birth else '',
                'Address': member.address,
                'Emergency Contact': member.emergency_contact,
                'Joined Date': str(member.joined_date),
                'Active': 'Yes' if member.is_active else 'No',
                'Deactivated At': str(member.deactivated_at) if member.deactivated_at else '',
            }
            
            if include_subscription:
                active_sub = member.active_subs[0] if member.active_subs else None
                row.update({
                    'Subscription Plan': active_sub.plan.name if active_sub else 'None',
                    'Subscription Status': active_sub.status if active_sub else 'N/A',
                    'Subscription Expiry': str(active_sub.end_date) if active_sub else '',
                })
            
            data.append(row)
        
        return ExportService.export_to_csv(data, 'members.csv')
    
    @staticmethod
    def export_attendance_csv(start_date=None, end_date=None) -> io.StringIO:
        """
        Export attendance records to CSV.
        
        Args:
            start_date: Filter start date
            end_date: Filter end date
            
        Returns:
            StringIO object with CSV content
        """
        from .models import Attendance
        
        today = timezone.localdate()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = today - timedelta(days=30)
        
        attendance = Attendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        ).select_related('member__user').order_by('-check_in')
        
        data = []
        for record in attendance:
            data.append({
                'Date': str(record.date),
                'Member': record.member.user.full_name,
                'Email': record.member.user.email,
                'Check In': record.check_in.strftime('%H:%M:%S'),
                'Check Out': record.check_out.strftime('%H:%M:%S') if record.check_out else '',
                'Duration (hours)': record.duration() or '',
            })
        
        return ExportService.export_to_csv(data, 'attendance.csv')
    
    @staticmethod
    def export_revenue_report_csv(start_date=None, end_date=None) -> io.StringIO:
        """
        Export revenue report to CSV.
        
        Args:
            start_date: Report start date
            end_date: Report end date
            
        Returns:
            StringIO object with CSV content
        """
        report = AnalyticsService.get_revenue_report(start_date, end_date)
        
        # Export daily revenue as CSV
        data = []
        for day in report['daily_revenue']:
            data.append({
                'Date': str(day['date']),
                'Revenue': str(day['total']),
                'Transactions': day['count'],
            })
        
        return ExportService.export_to_csv(data, 'revenue_report.csv')
