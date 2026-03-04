from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AdminProfile, Member, Staff
from .models import Attendance, MembershipPlan, Payment, Subscription
from .services import AttendanceService

User = get_user_model()


class AttendanceConcurrencyHardeningTests(TestCase):
	def setUp(self):
		self.staff_user = User.objects.create_user(
			email='staff-concurrency@test.com',
			username='staff_concurrency',
			password='testpass123',
			full_name='Staff Concurrency',
			is_verified=True,
		)
		Staff.objects.create(user=self.staff_user, department='Front Desk')

		member_user = User.objects.create_user(
			email='member-concurrency@test.com',
			username='member_concurrency',
			password='testpass123',
			full_name='Member Concurrency',
			is_verified=True,
		)
		self.member = Member.objects.create(user=member_user)
		self.plan = MembershipPlan.objects.create(
			name='Concurrency Plan',
			description='Plan for concurrency tests',
			price=Decimal('1000.00'),
			duration_days=30,
		)
		Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)

	def test_db_constraint_blocks_second_open_attendance(self):
		Attendance.objects.create(member=self.member)
		with self.assertRaises(IntegrityError):
			Attendance.objects.create(member=self.member)

	def test_service_returns_value_error_not_integrity_error(self):
		AttendanceService.check_in_member(self.member)
		with self.assertRaisesMessage(ValueError, 'already checked in'):
			AttendanceService.check_in_member(self.member)

	def test_checkin_view_returns_user_safe_message_on_duplicate(self):
		AttendanceService.check_in_member(self.member)
		self.client.login(username='staff_concurrency', password='testpass123')
		response = self.client.post(
			reverse('gym_management:attendance_checkin'),
			{'member_id': self.member.id},
			follow=True,
		)
		messages = [str(msg) for msg in get_messages(response.wsgi_request)]
		self.assertTrue(any('already checked in' in message for message in messages))


class TimezoneBoundaryHardeningTests(TestCase):
	def setUp(self):
		member_user = User.objects.create_user(
			email='member-timezone@test.com',
			username='member_timezone',
			password='testpass123',
			full_name='Member Timezone',
			is_verified=True,
		)
		self.member = Member.objects.create(user=member_user)
		self.plan = MembershipPlan.objects.create(
			name='Timezone Plan',
			description='Plan for timezone tests',
			price=Decimal('1200.00'),
			duration_days=30,
		)
		self.subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate(),
			status='active',
		)

	def test_subscription_active_boundary_uses_localdate(self):
		today = timezone.localdate()
		with patch('gym_management.models.timezone.localdate', return_value=today):
			self.assertTrue(self.subscription.is_active_subscription())
		with patch('gym_management.models.timezone.localdate', return_value=today + timedelta(days=1)):
			self.assertFalse(self.subscription.is_active_subscription())

	def test_check_in_expires_subscription_on_localdate_rollover(self):
		future_local_date = timezone.localdate() + timedelta(days=1)
		with patch('gym_management.services.timezone.localdate', return_value=future_local_date):
			with self.assertRaisesMessage(ValueError, 'expired'):
				AttendanceService.check_in_member(self.member)
		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.status, 'expired')


class LeastPrivilegeEnforcementTests(TestCase):
	def setUp(self):
		self.limited_admin = User.objects.create_user(
			email='limited-admin@test.com',
			username='limited_admin',
			password='testpass123',
			full_name='Limited Admin',
			is_verified=True,
		)
		AdminProfile.objects.create(
			user=self.limited_admin,
			can_manage_users=False,
			can_manage_payments=False,
			can_view_reports=False,
		)

		self.payments_admin = User.objects.create_user(
			email='payments-admin@test.com',
			username='payments_admin',
			password='testpass123',
			full_name='Payments Admin',
			is_verified=True,
		)
		AdminProfile.objects.create(
			user=self.payments_admin,
			can_manage_users=False,
			can_manage_payments=True,
			can_view_reports=False,
		)

	def test_limited_admin_is_denied_sensitive_lists(self):
		self.client.login(username='limited_admin', password='testpass123')
		self.assertEqual(self.client.get(reverse('gym_management:member_list')).status_code, 403)
		self.assertEqual(self.client.get(reverse('gym_management:payment_list')).status_code, 403)
		self.assertEqual(self.client.get(reverse('gym_management:subscription_list')).status_code, 403)

	def test_payments_admin_cannot_access_user_management(self):
		self.client.login(username='payments_admin', password='testpass123')
		self.assertEqual(self.client.get(reverse('gym_management:payment_list')).status_code, 200)
		self.assertEqual(self.client.get(reverse('gym_management:member_list')).status_code, 403)


class FinancialDeleteProtectionTests(TestCase):
	def setUp(self):
		member_user = User.objects.create_user(
			email='member-financial@test.com',
			username='member_financial',
			password='testpass123',
			full_name='Member Financial',
			is_verified=True,
		)
		self.member = Member.objects.create(user=member_user)
		self.plan = MembershipPlan.objects.create(
			name='Financial Plan',
			description='Plan for delete protection tests',
			price=Decimal('2000.00'),
			duration_days=30,
		)
		self.subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)
		self.payment = Payment.objects.create(
			subscription=self.subscription,
			amount=self.plan.price,
			payment_method='cash',
			status='completed',
		)

	def test_subscription_delete_is_protected_with_payments(self):
		with self.assertRaises(ProtectedError):
			self.subscription.delete()

	def test_member_delete_is_protected_with_subscriptions(self):
		with self.assertRaises(ProtectedError):
			self.member.delete()
