"""
Comprehensive security test suite for MScube Gym Management System.

Tests cover:
- IDOR vulnerabilities
- Authorization bypasses
- Payment tampering
- Rate limiting effectiveness
- Business logic integrity
- CSRF protection
- Mass assignment prevention
"""

import uuid
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.contrib.messages import get_messages
from django.utils import timezone

from accounts.models import Member, AdminProfile, Staff, Trainer
from gym_management.models import MembershipPlan, Subscription, Payment, Attendance
from gym_management.services import PaymentService, SubscriptionService

User = get_user_model()


class SecurityTestCase(TestCase):
    """Base test case with security test utilities."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            full_name='Test Admin',
            password='testpass123'
        )
        self.admin_user.is_verified = True
        self.admin_user.save()
        AdminProfile.objects.create(
            user=self.admin_user,
            can_manage_users=True,
            can_manage_payments=True,
            can_view_reports=True
        )
        
        self.member_user = User.objects.create_user(
            email='member@test.com',
            full_name='Test Member',
            password='testpass123'
        )
        self.member_user.is_verified = True
        self.member_user.save()
        self.member = Member.objects.create(user=self.member_user)
        
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            full_name='Test Staff',
            password='testpass123'
        )
        self.staff_user.is_verified = True
        self.staff_user.save()
        Staff.objects.create(user=self.staff_user, department='Front Desk')
        
        # Create membership plan
        self.plan = MembershipPlan.objects.create(
            name='Test Plan',
            description='Test plan',
            price=Decimal('100.00'),
            duration_days=30
        )
        
        self.client = Client()


class IDORVulnerabilityTests(SecurityTestCase):
    """Test for Insecure Direct Object Reference vulnerabilities."""
    
    def test_member_detail_requires_admin(self):
        """Test that member detail view requires admin access."""
        # Try to access as member
        self.client.login(email='member@test.com', password='testpass123')
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member.id]))
        self.assertEqual(response.status_code, 403)
        
        # Try to access as staff (should fail)
        self.client.login(email='staff@test.com', password='testpass123')
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member.id]))
        self.assertEqual(response.status_code, 403)
        
        # Admin should succeed
        self.client.login(email='admin@test.com', password='testpass123')
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_payment_detail_requires_admin_with_payment_permission(self):
        """Test payment detail requires specific admin permissions."""
        # Create subscription and payment
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        payment = Payment.objects.create(
            subscription=subscription,
            amount=self.plan.price,
            payment_method='cash',
            status='completed'
        )
        
        # Create admin without payment permission
        limited_admin = User.objects.create_user(
            email='limited@test.com',
            full_name='Limited Admin',
            password='testpass123'
        )
        limited_admin.is_verified = True
        limited_admin.save()
        AdminProfile.objects.create(
            user=limited_admin,
            can_manage_users=True,
            can_manage_payments=False,  # No payment permission
            can_view_reports=False,
        )
        
        # Limited admin should be denied
        self.client.login(email='limited@test.com', password='testpass123')
        response = self.client.get(reverse('gym_management:payment_detail', args=[payment.id]))
        self.assertEqual(response.status_code, 403)
        
        # Full admin should succeed
        self.client.login(email='admin@test.com', password='testpass123')
        response = self.client.get(reverse('gym_management:payment_detail', args=[payment.id]))
        self.assertEqual(response.status_code, 200)
    
    def test_attendance_checkout_ownership_validation(self):
        """Test attendance checkout validates staff scope."""
        # Create old open attendance (9 hours ago)
        old_attendance = Attendance.objects.create(member=self.member)
        old_checkin = timezone.now() - timedelta(hours=9)
        Attendance.objects.filter(pk=old_attendance.pk).update(
            check_in=old_checkin,
            date=timezone.localdate(),
        )
        old_attendance.refresh_from_db()
        
        # Staff should only be able to checkout recent attendance
        self.client.login(email='staff@test.com', password='testpass123')

        # Old attendance should be denied for staff
        response = self.client.post(reverse('gym_management:attendance_checkout', args=[old_attendance.id]))
        self.assertEqual(response.status_code, 403)
        
        # Admin should be able to checkout any attendance
        self.client.login(email='admin@test.com', password='testpass123')
        response = self.client.post(reverse('gym_management:attendance_checkout', args=[old_attendance.id]))
        self.assertEqual(response.status_code, 302)

        # Create a fresh open attendance after old one is closed
        attendance = Attendance.objects.create(member=self.member)
        self.client.login(email='staff@test.com', password='testpass123')
        response = self.client.post(reverse('gym_management:attendance_checkout', args=[attendance.id]))
        self.assertEqual(response.status_code, 302)


class PaymentTamperingTests(SecurityTestCase):
    """Test payment amount tampering protection."""
    
    def test_payment_amount_server_side_calculation(self):
        """Test payment amount is calculated server-side, not client-submitted."""
        # Create subscription
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        self.client.login(email='admin@test.com', password='testpass123')
        
        # Try to tamper with amount by posting different value
        response = self.client.post(reverse('gym_management:payment_create'), {
            'subscription': subscription.id,
            'payment_method': 'cash',
            'amount': '1.00',  # Attempt to tamper - should be ignored
        })
        
        # Check that payment was created with correct amount (from plan)
        payment = Payment.objects.filter(subscription=subscription).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, self.plan.price)  # Should be 100.00, not 1.00
        self.assertEqual(payment.amount, Decimal('100.00'))
    
    def test_payment_service_rejects_amount_mismatch(self):
        """Test that payment service validates amounts match subscription plans."""
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        # Create payment with wrong amount directly in DB (simulating tampered request)
        payment = Payment.objects.create(
            subscription=subscription,
            amount=Decimal('1.00'),  # Wrong amount
            payment_method='cash',
            status='pending'
        )
        
        # PaymentService should validate amount matches
        with self.assertRaisesMessage(ValueError, 'Payment amount does not match subscription plan price'):
            PaymentService.validate_payment_amount(payment)


class RateLimitingTests(SecurityTestCase):
    """Test rate limiting effectiveness."""
    
    def setUp(self):
        super().setUp()
        cache.clear()  # Clear cache before each test
    
    @override_settings(CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }
    })
    def test_attendance_checkin_rate_limiting(self):
        """Test attendance check-in is rate limited."""
        self.client.login(email='staff@test.com', password='testpass123')
        
        # Make requests above configured limit (60/m)
        for i in range(65):
            response = self.client.post(reverse('gym_management:attendance_checkin'), {
                'member_id': self.member.id,
            })
        
        # Should contain rate limit message
        messages = list(get_messages(response.wsgi_request))
        rate_limit_found = any('Too many check-in attempts' in str(m) for m in messages)
        self.assertTrue(rate_limit_found)
    
    @override_settings(CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache',
        }
    })
    def test_payment_create_rate_limiting(self):
        """Test payment creation is rate limited."""
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        self.client.login(email='admin@test.com', password='testpass123')
        
        # Make 20 requests (at limit for payment)
        for i in range(20):
            Payment.objects.create(
                subscription=subscription,
                amount=self.plan.price,
                payment_method='cash',
                status='pending'
            )
            response = self.client.post(reverse('gym_management:payment_create'), {
                'subscription': subscription.id,
                'payment_method': 'cash',
            })
        
        # 21st request should be rate limited
        response = self.client.post(reverse('gym_management:payment_create'), {
            'subscription': subscription.id,
            'payment_method': 'cash',
        })
        
        messages = list(get_messages(response.wsgi_request))
        rate_limit_found = any('payment attempts' in str(m) for m in messages)
        self.assertTrue(rate_limit_found)


class BusinessLogicIntegrityTests(SecurityTestCase):
    """Test business logic integrity and race conditions."""
    
    def test_single_active_subscription_constraint(self):
        """Test that members cannot have multiple active subscriptions."""
        # Create first subscription
        subscription1 = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='active'
        )
        
        # Try to create second active subscription - should fail
        with self.assertRaises(Exception):
            SubscriptionService.create_subscription_with_payment(
                self.member,
                self.plan,
                'cash'
            )
    
    def test_payment_idempotency(self):
        """Test payment completion is idempotent."""
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        payment = Payment.objects.create(
            subscription=subscription,
            amount=self.plan.price,
            payment_method='esewa',
            status='pending'
        )
        
        # Complete payment
        PaymentService.complete_payment(payment)
        payment.refresh_from_db()
        first_completed_at = payment.completed_at
        
        # Try to complete again - should be idempotent
        PaymentService.complete_payment(payment)
        payment.refresh_from_db()
        
        self.assertEqual(payment.completed_at, first_completed_at)
        self.assertEqual(payment.status, 'completed')
    
    def test_concurrent_subscription_creation_safety(self):
        """Test concurrent subscription creation is safe."""
        from django.db import transaction
        
        with transaction.atomic():
            SubscriptionService.create_subscription_with_payment(
                self.member,
                self.plan,
                'cash'
            )

            with self.assertRaises(ValueError):
                SubscriptionService.create_subscription_with_payment(
                    self.member,
                    self.plan,
                    'cash'
                )
        
        # Should only have one subscription
        self.assertEqual(self.member.subscriptions.count(), 1)


class CSRFProtectionTests(SecurityTestCase):
    """Test CSRF protection is working."""
    
    def test_csrf_token_required_for_payment_create(self):
        """Test CSRF token is required for payment creation."""
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(email='admin@test.com', password='testpass123')
        
        # Try POST without CSRF token - should fail
        response = csrf_client.post(reverse('gym_management:payment_create'), {
            'subscription': subscription.id,
            'payment_method': 'cash',
        })
        
        self.assertEqual(response.status_code, 403)  # CSRF failure
    
    def test_csrf_token_required_for_attendance_checkout(self):
        """Test CSRF token is required for attendance checkout."""
        attendance = Attendance.objects.create(member=self.member)
        
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(email='staff@test.com', password='testpass123')
        
        # Try POST without CSRF token
        response = csrf_client.post(reverse('gym_management:attendance_checkout', args=[attendance.id]))
        
        self.assertEqual(response.status_code, 403)  # CSRF failure


class MassAssignmentTests(SecurityTestCase):
    """Test mass assignment protection."""
    
    def test_payment_form_prevents_amount_tampering(self):
        """Test payment form doesn't accept tampered amount field."""
        from gym_management.forms import PaymentCreateForm
        
        subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        # Try to submit tampered data including amount
        form_data = {
            'subscription': subscription.id,
            'payment_method': 'cash',
            'amount': '1.00',  # Should be ignored
            'status': 'completed',  # Should be ignored
            'transaction_id': 'HACKED123'  # Should be ignored
        }
        
        form = PaymentCreateForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        payment = form.save()
        
        # Amount should be from plan, not form
        self.assertEqual(payment.amount, self.plan.price)
        self.assertNotEqual(payment.amount, Decimal('1.00'))
        
        # Status should be default, not form value
        self.assertEqual(payment.status, 'pending')
        
        # Transaction ID should be auto-generated, not form value
        self.assertNotEqual(payment.transaction_id, 'HACKED123')
        self.assertTrue(payment.transaction_id.startswith('TXN'))


class AuditLoggingTests(SecurityTestCase):
    """Test audit logging captures security events."""
    
    def test_sensitive_object_access_logged(self):
        """Test sensitive object access is logged."""
        with self.assertLogs('security.audit', level='WARNING') as cm:
            self.client.login(email='admin@test.com', password='testpass123')
            response = self.client.get(reverse('gym_management:member_detail', args=[self.member.id]))
            
            # Check log contains access info
            self.assertTrue(any('SENSITIVE_OBJECT_ACCESS' in log for log in cm.output))
            self.assertTrue(any('admin@test.com' in log for log in cm.output))
    
    def test_permission_denied_logged(self):
        """Test permission denied attempts are logged."""
        with self.assertLogs('security.audit', level='INFO') as cm:
            self.client.login(email='member@test.com', password='testpass123')

            self.client.get(reverse('gym_management:member_detail', args=[self.member.id]))
            
            # Check middleware audit log contains denied access status
            self.assertTrue(any('status=403' in log and '/management/members/' in log for log in cm.output))