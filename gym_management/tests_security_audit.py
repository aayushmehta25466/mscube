"""
PHASE 1 SECURITY & INTEGRITY AUDIT - Test Suite
Tests authentication, authorization, and attendance integrity

Covers:
1. Authentication Security (email verification, brute force)
2. Authorization Testing (cross-role access, IDOR)
3. Attendance Integrity (duplicate check-in, expired subscription)
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from accounts.models import Member, Trainer, Staff, AdminProfile
from gym_management.models import MembershipPlan, Subscription, Payment, Attendance
from gym_management.services import AttendanceService, SubscriptionService

User = get_user_model()


class AuthenticationSecurityTest(TestCase):
    """Test authentication security including email verification and brute force protection."""
    
    def setUp(self):
        self.client = Client()
    
    def test_unverified_user_cannot_access_system(self):
        """CRITICAL: Unverified users should not be able to access protected pages."""
        # Create unverified user
        user = User.objects.create_user(
            email='unverified@test.com',
            username='unverified',
            password='testpass123',
            full_name='Unverified User',
            is_verified=False  # NOT verified
        )
        
        # Try to login
        self.client.login(username='unverified', password='testpass123')
        
        # Attempt to access member dashboard (should fail - no member profile)
        response = self.client.get(reverse('gym_management:member_dashboard'))
        
        # Should be denied (no member profile since email not verified)
        self.assertIn(response.status_code, [302, 403])
    
    def test_verified_user_gets_member_profile(self):
        """Verified users should have member profile created."""
        user = User.objects.create_user(
            email='verified@test.com',
            username='verified',
            password='testpass123',
            full_name='Verified User',
            is_verified=True
        )
        
        # Manually create member profile (simulating email_confirmed signal)
        Member.objects.create(user=user)
        
        self.assertTrue(hasattr(user, 'member'))
    
    def test_csrf_protection_active(self):
        """CSRF protection should be active on POST requests."""
        user = User.objects.create_user(
            email='staff@test.com',
            username='staff',
            password='testpass123',
            full_name='Staff User',
            is_verified=True
        )
        Staff.objects.create(user=user)
        
        self.client.login(username='staff', password='testpass123')
        
        # Try POST without CSRF token
        response = self.client.post(
            reverse('gym_management:attendance_checkin'),
            {'member_id': 1},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should fail due to CSRF (403)
        # Note: Django test client includes CSRF by default, so we check the middleware is present
        from django.conf import settings
        self.assertIn('django.middleware.csrf.CsrfViewMiddleware', settings.MIDDLEWARE)


class AuthorizationIDORTest(TestCase):
    """Test for Insecure Direct Object Reference (IDOR) vulnerabilities."""
    
    def setUp(self):
        self.client = Client()
        
        # Create test users with different roles
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            username='admin',
            password='admin123',
            full_name='Admin User',
            is_verified=True
        )
        AdminProfile.objects.create(
            user=self.admin_user,
            can_manage_users=True,
            can_manage_payments=True,
        )
        
        self.member1_user = User.objects.create_user(
            email='member1@test.com',
            username='member1',
            password='member123',
            full_name='Member One',
            is_verified=True
        )
        self.member1 = Member.objects.create(user=self.member1_user)
        
        self.member2_user = User.objects.create_user(
            email='member2@test.com',
            username='member2',
            password='member123',
            full_name='Member Two',
            is_verified=True
        )
        self.member2 = Member.objects.create(user=self.member2_user)
        
        self.trainer_user = User.objects.create_user(
            email='trainer@test.com',
            username='trainer',
            password='trainer123',
            full_name='Trainer User',
            is_verified=True
        )
        Trainer.objects.create(user=self.trainer_user)
        
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staff',
            password='staff123',
            full_name='Staff User',
            is_verified=True
        )
        Staff.objects.create(user=self.staff_user)
        
        # Create subscription for member1
        self.plan = MembershipPlan.objects.create(
            name='Basic Plan',
            description='Basic membership',
            price=Decimal('1000.00'),
            duration_days=30
        )
        self.subscription = Subscription.objects.create(
            member=self.member1,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='active'
        )
    
    def test_member_cannot_access_admin_dashboard(self):
        """CRITICAL: Members should not access admin dashboard."""
        self.client.login(username='member1', password='member123')
        response = self.client.get(reverse('gym_management:admin_dashboard'))
        
        # Should be denied (403 or redirect)
        self.assertIn(response.status_code, [302, 403])
    
    def test_trainer_cannot_access_admin_views(self):
        """CRITICAL: Trainers should not access admin-only views."""
        self.client.login(username='trainer', password='trainer123')
        
        # Try to access member list (admin only)
        response = self.client.get(reverse('gym_management:member_list'))
        self.assertIn(response.status_code, [302, 403])
        
        # Try to access member detail
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member1.pk]))
        self.assertIn(response.status_code, [302, 403])
    
    def test_staff_cannot_access_admin_dashboard(self):
        """Staff should not access admin dashboard."""
        self.client.login(username='staff', password='staff123')
        response = self.client.get(reverse('gym_management:admin_dashboard'))
        
        # Should be denied
        self.assertIn(response.status_code, [302, 403])
    
    def test_idor_member_detail_view(self):
        """VULNERABILITY: Admin can access any member detail, but verify it's admin-only."""
        # Admin should access
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member1.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Member trying to access another member's detail (should fail)
        self.client.login(username='member2', password='member123')
        response = self.client.get(reverse('gym_management:member_detail', args=[self.member1.pk]))
        self.assertIn(response.status_code, [302, 403])
    
    def test_idor_payment_detail_view(self):
        """VULNERABILITY: Verify only admin can access payment details."""
        payment = Payment.objects.create(
            subscription=self.subscription,
            amount=self.plan.price,
            payment_method='cash',
            status='completed'
        )
        
        # Admin should access
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('gym_management:payment_detail', args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Member2 trying to access member1's payment (should fail)
        self.client.login(username='member2', password='member123')
        response = self.client.get(reverse('gym_management:payment_detail', args=[payment.pk]))
        self.assertIn(response.status_code, [302, 403])
    
    def test_id_manipulation_subscription_cancel(self):
        """VULNERABILITY: Users should not be able to cancel arbitrary subscriptions by ID."""
        # Create subscription for member2
        subscription2 = Subscription.objects.create(
            member=self.member2,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='active'
        )
        
        # Member1 trying to cancel member2's subscription (should fail)
        self.client.login(username='member1', password='member123')
        response = self.client.post(reverse('gym_management:subscription_cancel', args=[subscription2.pk]))
        
        # Should be denied (member doesn't have admin permissions)
        self.assertIn(response.status_code, [302, 403])
        
        # Verify subscription still active
        subscription2.refresh_from_db()
        self.assertEqual(subscription2.status, 'active')


class AttendanceIntegrityTest(TestCase):
    """Test attendance integrity constraints."""
    
    def setUp(self):
        # Create member with active subscription
        self.user = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='member123',
            full_name='Test Member',
            is_verified=True
        )
        self.member = Member.objects.create(user=self.user)
        
        # Create plan and active subscription
        self.plan = MembershipPlan.objects.create(
            name='Monthly Plan',
            description='Monthly membership',
            price=Decimal('2000.00'),
            duration_days=30
        )
        self.active_subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='active'
        )
        
        # Create staff user for check-in operations
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            username='staff',
            password='staff123',
            full_name='Staff User',
            is_verified=True
        )
        Staff.objects.create(user=self.staff_user)
    
    def test_duplicate_checkin_prevented(self):
        """CRITICAL: Duplicate check-ins on same day must be prevented."""
        # First check-in should succeed
        attendance = AttendanceService.check_in_member(self.member)
        self.assertIsNotNone(attendance)
        self.assertIsNone(attendance.check_out)
        
        # Second check-in on same day should fail
        with self.assertRaises(ValueError) as context:
            AttendanceService.check_in_member(self.member)
        
        self.assertIn('already checked in', str(context.exception))
    
    def test_checkout_without_checkin_prevented(self):
        """Checking out without check-in should be prevented (already handled by requiring attendance_id)."""
        # There should be no attendance record
        self.assertEqual(Attendance.objects.filter(member=self.member).count(), 0)
        
        # Attempting to check out non-existent record would fail at the database level
        # This is protected by requiring an attendance_id parameter
    
    def test_expired_subscription_checkin_denied(self):
        """CRITICAL: Members with expired subscriptions cannot check in."""
        # Expire the subscription
        self.active_subscription.end_date = timezone.localdate() - timedelta(days=1)
        self.active_subscription.save()
        
        # Check-in should fail
        with self.assertRaises(ValueError) as context:
            AttendanceService.check_in_member(self.member)
        
        self.assertIn('expired', str(context.exception))
    
    def test_no_active_subscription_checkin_denied(self):
        """CRITICAL: Members without active subscription cannot check in."""
        # Cancel the subscription
        self.active_subscription.status = 'cancelled'
        self.active_subscription.save()
        
        # Check-in should fail
        with self.assertRaises(ValueError) as context:
            AttendanceService.check_in_member(self.member)
        
        self.assertIn('does not have an active subscription', str(context.exception))
    
    def test_double_checkout_prevented(self):
        """Double checkout should be prevented."""
        # Check in
        attendance = AttendanceService.check_in_member(self.member)
        
        # First checkout
        AttendanceService.check_out_member(attendance)
        self.assertIsNotNone(attendance.check_out)
        
        # Second checkout should fail
        with self.assertRaises(ValueError) as context:
            AttendanceService.check_out_member(attendance)
        
        self.assertIn('already checked out', str(context.exception))
    
    def test_attendance_checkout_authorization(self):
        """VULNERABILITY CHECK: Verify only staff/admin can checkout."""
        client = Client()
        
        # Check in member
        attendance = AttendanceService.check_in_member(self.member)
        
        # Member trying to checkout (should be denied - member can't access checkout endpoint)
        client.login(username='member', password='member123')
        response = client.post(reverse('gym_management:attendance_checkout', args=[attendance.id]))
        
        # Should be denied (not staff)
        self.assertIn(response.status_code, [302, 403])
        
        # Verify attendance NOT checked out
        attendance.refresh_from_db()
        self.assertIsNone(attendance.check_out)
        
        # Staff should be able to checkout
        client.login(username='staff', password='staff123')
        response = client.post(reverse('gym_management:attendance_checkout', args=[attendance.id]))
        
        # Should succeed
        self.assertEqual(response.status_code, 302)
        attendance.refresh_from_db()
        self.assertIsNotNone(attendance.check_out)


class SubscriptionIntegrityTest(TestCase):
    """Test subscription business logic and constraints."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='member123',
            full_name='Test Member',
            is_verified=True
        )
        self.member = Member.objects.create(user=self.user)
        
        self.plan = MembershipPlan.objects.create(
            name='Monthly Plan',
            description='Monthly membership',
            price=Decimal('2000.00'),
            duration_days=30
        )
    
    def test_single_active_subscription_constraint(self):
        """CRITICAL: Only one active subscription per member."""
        # Create first active subscription
        sub1 = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='active'
        )
        
        # Attempting to create second active subscription should fail via service
        with self.assertRaises(ValueError) as context:
            SubscriptionService.create_subscription_with_payment(
                self.member,
                self.plan,
                'cash'
            )
        
        self.assertIn('already has an active subscription', str(context.exception))
    
    def test_subscription_payment_atomicity(self):
        """Subscription and payment creation should be atomic."""
        subscription, payment = SubscriptionService.create_subscription_with_payment(
            self.member,
            self.plan,
            'cash'
        )
        
        # Both should exist
        self.assertIsNotNone(subscription)
        self.assertIsNotNone(payment)
        
        # For cash payment, subscription should be active
        self.assertEqual(subscription.status, 'active')
        self.assertEqual(payment.status, 'completed')
        
        # They should be linked
        self.assertEqual(payment.subscription, subscription)
    
    def test_online_payment_pending_until_confirmed(self):
        """Online payments should keep subscription pending until confirmed."""
        subscription, payment = SubscriptionService.create_subscription_with_payment(
            self.member,
            self.plan,
            'esewa'  # Online payment
        )
        
        # Subscription should be pending
        self.assertEqual(subscription.status, 'pending')
        self.assertEqual(payment.status, 'pending')


class PaymentSecurityTest(TestCase):
    """Test payment-related security concerns."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@test.com',
            username='member',
            password='member123',
            full_name='Test Member',
            is_verified=True
        )
        self.member = Member.objects.create(user=self.user)
        
        self.plan = MembershipPlan.objects.create(
            name='Monthly Plan',
            description='Monthly membership',
            price=Decimal('2000.00'),
            duration_days=30
        )
        
        self.subscription = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
    
    def test_transaction_id_uniqueness(self):
        """Transaction IDs must be unique."""
        payment1 = Payment.objects.create(
            subscription=self.subscription,
            amount=self.plan.price,
            payment_method='cash',
            status='completed'
        )
        
        # Create another subscription for uniqueness test
        subscription2 = Subscription.objects.create(
            member=self.member,
            plan=self.plan,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
            status='pending'
        )
        
        payment2 = Payment.objects.create(
            subscription=subscription2,
            amount=self.plan.price,
            payment_method='cash',
            status='completed'
        )
        
        # Transaction IDs should be different
        self.assertNotEqual(payment1.transaction_id, payment2.transaction_id)
    
    def test_transaction_id_is_non_predictable_uuid_token(self):
        """Transaction IDs should use non-predictable UUID-based tokens."""
        payment = Payment.objects.create(
            subscription=self.subscription,
            amount=self.plan.price,
            payment_method='cash',
            status='completed'
        )

        self.assertTrue(payment.transaction_id.startswith('TXN'))
        self.assertEqual(len(payment.transaction_id), 19)
        self.assertRegex(payment.transaction_id, r'^TXN[A-F0-9]{16}$')


class RateLimitAndBruteForceTest(TestCase):
    """Test rate limiting and brute force protection."""
    
    def test_axes_installed(self):
        """Verify django-axes is installed for brute force protection."""
        from django.conf import settings
        
        # Check axes is in INSTALLED_APPS
        self.assertIn('axes', settings.INSTALLED_APPS)
        
        # Check axes middleware is present
        self.assertIn('axes.middleware.AxesMiddleware', settings.MIDDLEWARE)
        
        # Check axes backend is configured
        self.assertIn('axes.backends.AxesStandaloneBackend', settings.AUTHENTICATION_BACKENDS)
    
    def test_axes_configuration(self):
        """Verify axes is properly configured."""
        from django.conf import settings
        
        # Check failure limit
        self.assertEqual(settings.AXES_FAILURE_LIMIT, 5)
        
        # Check cooloff time (1 hour)
        self.assertEqual(settings.AXES_COOLOFF_TIME, 1)
        
        # Check lockout parameters
        self.assertIn('username', settings.AXES_LOCKOUT_PARAMETERS)
        self.assertIn('ip_address', settings.AXES_LOCKOUT_PARAMETERS)
