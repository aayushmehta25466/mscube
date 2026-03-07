from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AdminProfile, Member, Staff
from .forms import (
	PaymentAdminForm, PaymentCreateForm,
	SubscriptionAdminForm, SubscriptionBaseForm, SubscriptionCreateForm, SubscriptionForm, SubscriptionUpdateForm,
)
from .models import Attendance, CheckInSession, MembershipPlan, Payment, Subscription
from .services import AttendanceService, PaymentService, SubscriptionService
from .views import SubscriptionCreateView, SubscriptionUpdateView

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
		"""Subscriptions with payments should raise ValidationError on delete."""
		with self.assertRaises(ValidationError):
			self.subscription.delete()

	def test_member_delete_is_protected_with_subscriptions(self):
		"""Members with subscriptions should raise ValidationError on delete."""
		with self.assertRaises(ValidationError):
			self.member.delete()

class MemberDeactivationTests(TestCase):
	"""Tests for member deactivation service including edge cases with ActiveMemberManager."""
	
	def setUp(self):
		self.user = User.objects.create_user(
			email='deactivation-test@example.com',
			username='deactivation_test',
			password='testpass123',
			full_name='Deactivation Test User',
			is_verified=True,
		)
		self.member = Member.objects.create(user=self.user)
		self.plan = MembershipPlan.objects.create(
			name='Deactivation Test Plan',
			description='Plan for testing',
			price=Decimal('1500.00'),
			duration_days=30,
		)
	
	def test_deactivate_active_member_succeeds(self):
		"""Deactivating an active member should work correctly."""
		from .services import MemberService
		
		# Create active subscription
		Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)
		
		# Deactivate member
		deactivated = MemberService.deactivate_member(self.member, reason='Testing')
		
		# Verify deactivation
		self.assertFalse(deactivated.is_active)
		self.assertIsNotNone(deactivated.deactivated_at)
		
		# Verify subscriptions were cancelled
		self.assertEqual(
			deactivated.subscriptions.filter(status='active').count(),
			0
		)
	
	def test_deactivate_inactive_member_raises_value_error(self):
		"""Attempting to deactivate an already inactive member should raise ValueError."""
		from .services import MemberService
		
		# First deactivation
		MemberService.deactivate_member(self.member, reason='First deactivation')
		
		# Refresh from database using all_objects
		self.member = Member.all_objects.get(pk=self.member.pk)
		
		# Second deactivation attempt should raise ValueError
		with self.assertRaises(ValueError) as context:
			MemberService.deactivate_member(self.member, reason='Second attempt')
		
		self.assertIn('already inactive', str(context.exception))
	
	def test_inactive_member_not_in_default_queryset(self):
		"""Inactive members should not appear in Member.objects queries."""
		from .services import MemberService
		
		# Member exists in default queryset
		self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())
		
		# Deactivate member
		MemberService.deactivate_member(self.member)
		
		# Member should not exist in default queryset
		self.assertFalse(Member.objects.filter(pk=self.member.pk).exists())
		
		# But should exist in all_objects queryset
		self.assertTrue(Member.all_objects.filter(pk=self.member.pk).exists())


class FinancialIntegrityHardeningTests(TestCase):
	def setUp(self):
		self.member_user = User.objects.create_user(
			email='financial-member@test.com',
			username='financial_member',
			password='testpass123',
			full_name='Financial Member',
			is_verified=True,
		)
		self.member = Member.objects.create(user=self.member_user)
		self.plan = MembershipPlan.objects.create(
			name='Financial Integrity Plan',
			description='Plan for financial integrity tests',
			price=Decimal('2500.00'),
			duration_days=30,
		)

	def test_subscription_service_blocks_duplicate_active_subscription(self):
		Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)

		with self.assertRaisesMessage(ValidationError, 'Member already has an active subscription.'):
			SubscriptionService.create_subscription(self.member, self.plan)

	def test_payment_form_only_lists_pending_subscriptions(self):
		pending_subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='pending',
		)
		active_subscription = Subscription.objects.create(
			member=Member.objects.create(
				user=User.objects.create_user(
					email='active-member@test.com',
					username='active_member',
					password='testpass123',
					full_name='Active Member',
					is_verified=True,
				)
			),
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)

		form = PaymentCreateForm()
		queryset_ids = list(form.fields['subscription'].queryset.values_list('pk', flat=True))

		self.assertIn(pending_subscription.pk, queryset_ids)
		self.assertNotIn(active_subscription.pk, queryset_ids)
		self.assertEqual(
			form.fields['subscription'].label_from_instance(pending_subscription),
			f'{self.member.user.full_name} - {self.plan.name} - Pending',
		)

	def test_payment_form_accepts_prefilled_subscription_instance(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='pending',
		)

		form = PaymentCreateForm(initial={
			'subscription': subscription,
		})

		self.assertIn(
			subscription.pk,
			list(form.fields['subscription'].queryset.values_list('pk', flat=True)),
		)

	def test_payment_form_rejects_duplicate_payment_for_subscription(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='pending',
		)
		Payment.objects.create(
			subscription=subscription,
			amount=self.plan.price,
			payment_method='cash',
			status='pending',
		)

		form = PaymentCreateForm(data={
			'subscription': subscription.pk,
			'payment_method': 'cash',
		})

		self.assertFalse(form.is_valid())
		self.assertIn('Payment already recorded for this subscription.', form.errors['__all__'])

	def test_payment_service_completes_payment_and_refreshes_subscription_dates(self):
		stale_start_date = timezone.localdate() - timedelta(days=10)
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=stale_start_date,
			end_date=stale_start_date + timedelta(days=30),
			status='pending',
		)

		payment = PaymentService.create_payment(subscription, 'cash')
		payment, _ = PaymentService.complete_payment(payment)
		subscription.refresh_from_db()

		self.assertEqual(payment.status, 'completed')
		self.assertEqual(subscription.status, 'active')
		self.assertEqual(subscription.start_date, timezone.localdate())
		self.assertEqual(
			subscription.end_date,
			timezone.localdate() + timedelta(days=self.plan.duration_days),
		)


class SubscriptionAndPaymentAdminHardeningTests(TestCase):
	def setUp(self):
		self.member = Member.objects.create(
			user=User.objects.create_user(
				email='admin-hardening-member@test.com',
				username='admin_hardening_member',
				password='testpass123',
				full_name='Admin Hardening Member',
				is_verified=True,
			)
		)
		self.plan = MembershipPlan.objects.create(
			name='Admin Hardening Plan',
			description='Plan for admin form validation tests',
			price=Decimal('1900.00'),
			duration_days=30,
		)

	def test_subscription_admin_form_blocks_manual_active_creation(self):
		form = SubscriptionAdminForm(data={
			'member': self.member.pk,
			'plan': self.plan.pk,
			'start_date': timezone.localdate(),
			'end_date': timezone.localdate() + timedelta(days=30),
			'status': 'active',
		})

		self.assertFalse(form.is_valid())
		self.assertIn(
			'New subscriptions must start as pending until payment is completed.',
			form.errors['status'],
		)

	def test_payment_admin_form_blocks_non_pending_subscription(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)

		form = PaymentAdminForm(data={
			'subscription': subscription.pk,
			'payment_method': 'cash',
			'status': 'completed',
			'notes': '',
			'esewa_transaction_code': '',
			'esewa_ref_id': '',
		})

		self.assertFalse(form.is_valid())
		self.assertIn('Payment allowed only for pending subscriptions.', form.errors['__all__'])


class SubscriptionCreationFormOrderingTests(TestCase):
	def setUp(self):
		self.plan = MembershipPlan.objects.create(
			name='Ordering Plan',
			description='Plan for subscription member ordering',
			price=Decimal('1500.00'),
			duration_days=30,
		)

		self.pending_member = self._create_member('Pending Member', 'pending_member')
		self.active_member = self._create_member('Active Member', 'ordered_active_member')
		self.expired_member = self._create_member('Expired Member', 'expired_member')
		self.cancelled_member = self._create_member('Cancelled Member', 'cancelled_member')

		Subscription.objects.create(
			member=self.pending_member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='pending',
		)
		Subscription.objects.create(
			member=self.active_member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)
		Subscription.objects.create(
			member=self.expired_member,
			plan=self.plan,
			start_date=timezone.localdate() - timedelta(days=60),
			end_date=timezone.localdate() - timedelta(days=30),
			status='expired',
		)
		Subscription.objects.create(
			member=self.cancelled_member,
			plan=self.plan,
			start_date=timezone.localdate() - timedelta(days=60),
			end_date=timezone.localdate() - timedelta(days=30),
			status='cancelled',
		)

	def _create_member(self, full_name, username):
		return Member.objects.create(
			user=User.objects.create_user(
				email=f'{username}@test.com',
				username=username,
				password='testpass123',
				full_name=full_name,
				is_verified=True,
			)
		)

	def test_subscription_create_form_orders_and_labels_members_by_subscription_status(self):
		form = SubscriptionCreateForm()
		members = list(form.fields['member'].queryset)

		self.assertEqual(
			[member.pk for member in members[:4]],
			[
				self.pending_member.pk,
				self.active_member.pk,
				self.expired_member.pk,
				self.cancelled_member.pk,
			],
		)
		self.assertEqual(
			form.fields['member'].label_from_instance(self.pending_member),
			'Pending Member (Pending)',
		)
		self.assertEqual(
			form.fields['member'].label_from_instance(self.active_member),
			'Active Member (Active)',
		)


class SubscriptionDateConsistencyTests(TestCase):
	"""Validates start_date widget and shared form usage for subscription create/update."""

	def setUp(self):
		self.plan = MembershipPlan.objects.create(
			name='Date Test Plan',
			price=Decimal('1500.00'),
			duration_days=30,
		)
		self.user = User.objects.create_user(
			email='datetest@test.com',
			username='datetest_user',
			password='testpass123',
			full_name='Date Test User',
			is_verified=True,
		)
		self.member = Member.objects.create(user=self.user)

	# ── Widget identity ──────────────────────────────────────────────────────

	def test_create_form_start_date_uses_html5_date_widget(self):
		form = SubscriptionForm()
		widget = form.fields['start_date'].widget
		self.assertIsInstance(widget, forms.DateInput)
		self.assertEqual(widget.input_type, 'date')
		self.assertIn('[color-scheme:dark]', widget.attrs.get('class', ''))

	def test_update_form_start_date_uses_html5_date_widget(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=self.plan.duration_days),
			status='pending',
		)
		form = SubscriptionForm(instance=subscription)
		widget = form.fields['start_date'].widget
		self.assertIsInstance(widget, forms.DateInput)
		self.assertEqual(widget.input_type, 'date')
		self.assertIn('[color-scheme:dark]', widget.attrs.get('class', ''))

	def test_both_forms_share_widget_attrs(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=self.plan.duration_days),
			status='pending',
		)
		create_form = SubscriptionForm()
		update_form = SubscriptionForm(instance=subscription)
		self.assertEqual(
			create_form.fields['start_date'].widget.attrs,
			update_form.fields['start_date'].widget.attrs,
			msg='start_date widget attrs must be identical between create and update forms.',
		)
		self.assertFalse(update_form.fields['member'].required)

	# ── create form clean_start_date ─────────────────────────────────────────

	def test_create_form_rejects_past_start_date(self):
		past = timezone.localdate() - timedelta(days=1)
		form = SubscriptionForm(data={
			'member': self.member.pk,
			'plan': self.plan.pk,
			'start_date': past.isoformat(),
		})
		self.assertFalse(form.is_valid())
		self.assertIn('Start date cannot be in the past.', form.errors.get('start_date', []))

	def test_create_form_accepts_today_start_date(self):
		form = SubscriptionForm(data={
			'member': self.member.pk,
			'plan': self.plan.pk,
			'start_date': timezone.localdate().isoformat(),
		})
		# Field-level clean should pass (form may still be invalid due to active-subscription check)
		self.assertNotIn('start_date', form.errors)

	def test_create_form_accepts_future_start_date(self):
		future = timezone.localdate() + timedelta(days=7)
		form = SubscriptionForm(data={
			'member': self.member.pk,
			'plan': self.plan.pk,
			'start_date': future.isoformat(),
		})
		self.assertNotIn('start_date', form.errors)

	# ── update form clean_start_date ─────────────────────────────────────────

	def test_update_form_allows_retaining_historical_start_date(self):
		"""Admin must be able to save an existing subscription whose start_date is in the past."""
		past = timezone.localdate() - timedelta(days=30)
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=past,
			end_date=past + timedelta(days=self.plan.duration_days),
			status='active',
		)
		form = SubscriptionUpdateForm(
			data={
				'plan': self.plan.pk,
				'start_date': past.isoformat(),
			},
			instance=subscription,
		)
		self.assertNotIn('start_date', form.errors)

	def test_update_form_rejects_changing_to_different_past_start_date(self):
		"""Admin must not be able to move start_date to a *different* past date."""
		original_start = timezone.localdate() - timedelta(days=10)
		different_past = timezone.localdate() - timedelta(days=20)
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=original_start,
			end_date=original_start + timedelta(days=self.plan.duration_days),
			status='active',
		)
		form = SubscriptionUpdateForm(
			data={
				'plan': self.plan.pk,
				'start_date': different_past.isoformat(),
			},
			instance=subscription,
		)
		self.assertFalse(form.is_valid())
		self.assertIn('Start date cannot be in the past.', form.errors.get('start_date', []))

	# ── Inheritance hierarchy ────────────────────────────────────────────────

	def test_both_forms_inherit_from_base(self):
		self.assertIs(SubscriptionCreateForm, SubscriptionForm)
		self.assertIs(SubscriptionUpdateForm, SubscriptionForm)
		self.assertTrue(issubclass(SubscriptionCreateForm, SubscriptionBaseForm))
		self.assertTrue(issubclass(SubscriptionUpdateForm, SubscriptionBaseForm))

	def test_both_views_use_subscription_form(self):
		self.assertIs(SubscriptionCreateView.form_class, SubscriptionForm)
		self.assertIs(SubscriptionUpdateView.form_class, SubscriptionForm)

	def test_update_form_does_not_expose_payment_or_status_fields(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=self.plan.duration_days),
			status='pending',
		)
		form = SubscriptionForm(instance=subscription)
		self.assertNotIn('payment_method', form.fields)
		self.assertNotIn('status', form.fields)
		self.assertNotIn('end_date', form.fields)
		self.assertIn('cancel the current subscription', form.fields['plan'].help_text)


class SubscriptionUpdateWorkflowTests(TestCase):
	def setUp(self):
		self.admin_user = User.objects.create_user(
			email='subscription-admin@test.com',
			username='subscription_admin',
			password='testpass123',
			full_name='Subscription Admin',
			is_verified=True,
		)
		AdminProfile.objects.create(
			user=self.admin_user,
			can_manage_users=False,
			can_manage_payments=True,
			can_view_reports=False,
		)
		self.client.login(username='subscription_admin', password='testpass123')

		self.member = Member.objects.create(
			user=User.objects.create_user(
				email='subscription-member@test.com',
				username='subscription_member',
				password='testpass123',
				full_name='Subscription Member',
				is_verified=True,
			)
		)
		self.old_plan = MembershipPlan.objects.create(
			name='Current Plan',
			description='Current subscription plan',
			price=Decimal('1500.00'),
			duration_days=30,
		)
		self.new_plan = MembershipPlan.objects.create(
			name='Replacement Plan',
			description='Replacement subscription plan',
			price=Decimal('2200.00'),
			duration_days=60,
		)

	def test_plan_change_rolls_back_cancellation_on_failure(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.old_plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=self.old_plan.duration_days),
			status='active',
		)

		with patch('gym_management.services.SubscriptionService.create_subscription', side_effect=ValidationError('creation failed')):
			with self.assertRaisesMessage(ValidationError, 'creation failed'):
				SubscriptionService.update_subscription(
					subscription=subscription,
					plan=self.new_plan,
					start_date=timezone.localdate() + timedelta(days=1),
				)

		subscription.refresh_from_db()
		self.assertEqual(subscription.status, 'active')

	def test_same_plan_update_does_not_create_payment_or_new_subscription(self):
		start_date = timezone.localdate() + timedelta(days=2)
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.old_plan,
			start_date=start_date,
			end_date=start_date + timedelta(days=self.old_plan.duration_days),
			status='pending',
		)
		new_start_date = start_date + timedelta(days=3)

		response = self.client.post(
			reverse('gym_management:subscription_update', kwargs={'pk': subscription.pk}),
			{
				'plan': self.old_plan.pk,
				'start_date': new_start_date.isoformat(),
			},
			follow=True,
		)

		subscription.refresh_from_db()
		self.assertEqual(Subscription.objects.filter(member=self.member).count(), 1)
		self.assertEqual(Payment.objects.count(), 0)
		self.assertEqual(subscription.start_date, new_start_date)
		self.assertEqual(
			subscription.end_date,
			new_start_date + timedelta(days=self.old_plan.duration_days),
		)
		messages = [str(message) for message in get_messages(response.wsgi_request)]
		self.assertIn('Subscription updated successfully.', messages)

	def test_plan_change_cancels_old_subscription_and_redirects_to_payment_create(self):
		start_date = timezone.localdate()
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.old_plan,
			start_date=start_date,
			end_date=start_date + timedelta(days=self.old_plan.duration_days),
			status='active',
		)
		Payment.objects.create(
			subscription=subscription,
			amount=self.old_plan.price,
			payment_method='cash',
			status='completed',
		)
		new_start_date = timezone.localdate() + timedelta(days=5)

		response = self.client.post(
			reverse('gym_management:subscription_update', kwargs={'pk': subscription.pk}),
			{
				'plan': self.new_plan.pk,
				'start_date': new_start_date.isoformat(),
			},
			follow=True,
		)

		subscription.refresh_from_db()
		new_subscription = Subscription.objects.exclude(pk=subscription.pk).get(member=self.member)

		self.assertEqual(subscription.status, 'cancelled')
		self.assertEqual(subscription.plan, self.old_plan)
		self.assertEqual(subscription.start_date, start_date)
		self.assertEqual(subscription.end_date, start_date + timedelta(days=self.old_plan.duration_days))
		self.assertEqual(subscription.payments.count(), 1)
		self.assertEqual(new_subscription.plan, self.new_plan)
		self.assertEqual(new_subscription.status, 'pending')
		self.assertEqual(new_subscription.start_date, new_start_date)
		self.assertEqual(
			new_subscription.end_date,
			new_start_date + timedelta(days=self.new_plan.duration_days),
		)
		self.assertEqual(new_subscription.payments.count(), 0)
		self.assertEqual(Payment.objects.count(), 1)
		self.assertEqual(
			response.redirect_chain[0][0],
			f"{reverse('gym_management:payment_create')}?subscription={new_subscription.pk}",
		)
		messages = [str(message) for message in get_messages(response.wsgi_request)]
		self.assertIn('New subscription created. Please record payment.', messages)

	def test_update_page_does_not_render_payment_or_status_fields(self):
		subscription = Subscription.objects.create(
			member=self.member,
			plan=self.old_plan,
			start_date=timezone.localdate() + timedelta(days=1),
			end_date=timezone.localdate() + timedelta(days=1 + self.old_plan.duration_days),
			status='pending',
		)

		response = self.client.get(reverse('gym_management:subscription_update', kwargs={'pk': subscription.pk}))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'name="start_date"', html=False)
		self.assertContains(response, 'type="date"', html=False)
		self.assertNotContains(response, 'name="payment_method"', html=False)
		self.assertNotContains(response, 'name="status"', html=False)
		self.assertNotContains(response, 'name="end_date"', html=False)
		self.assertNotContains(response, 'Record a Payment for This Update', html=False)


@override_settings(
	GYM_LATITUDE=27.7000,
	GYM_LONGITUDE=85.3333,
	GYM_RADIUS_METERS=100.0,
	GYM_QR_SESSION_TTL_SECONDS=60,
)
class QRSelfServiceHardeningTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			email='phase3-member@example.com',
			username='phase3_member',
			password='testpass123',
			full_name='Phase 3 Member',
			is_verified=True,
		)
		self.member = Member.objects.create(user=self.user)
		self.plan = MembershipPlan.objects.create(
			name='Phase 3 Plan',
			description='Plan for QR hardening tests',
			price=Decimal('1800.00'),
			duration_days=30,
		)
		Subscription.objects.create(
			member=self.member,
			plan=self.plan,
			start_date=timezone.localdate(),
			end_date=timezone.localdate() + timedelta(days=30),
			status='active',
		)
		self.client.force_login(self.user)
		self.nearby_payload = {
			'latitude': '27.7000',
			'longitude': '85.3333',
		}
		self.far_payload = {
			'latitude': '27.7100',
			'longitude': '85.3433',
		}

	def _generate_token(self, route_name):
		response = self.client.get(reverse(route_name))
		self.assertEqual(response.status_code, 302)
		location = response['Location']
		parsed = urlparse(location)
		self.assertIn('token', parse_qs(parsed.query))
		return parse_qs(parsed.query)['token'][0]

	def test_successful_self_check_in(self):
		token = self._generate_token('gym_management:self_checkin')
		response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.nearby_payload},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['check_in_success'])
		self.assertEqual(Attendance.objects.filter(member=self.member).count(), 1)
		self.assertTrue(CheckInSession.objects.get(pk=token).used)

	def test_check_in_outside_gym_radius_is_rejected(self):
		token = self._generate_token('gym_management:self_checkin')
		response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.far_payload},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Attendance.objects.filter(member=self.member).count(), 0)
		self.assertEqual(
			response.context['error_message'],
			'You must be physically near the gym to check in.',
		)
		self.assertFalse(CheckInSession.objects.get(pk=token).used)

	def test_expired_token_is_rejected(self):
		token = self._generate_token('gym_management:self_checkin')
		CheckInSession.objects.filter(pk=token).update(expires_at=timezone.now() - timedelta(seconds=1))

		response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.nearby_payload},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Attendance.objects.filter(member=self.member).count(), 0)
		self.assertEqual(
			response.context['error_message'],
			AttendanceService.EXPIRED_QR_MESSAGE,
		)

	def test_duplicate_open_attendance_is_rejected(self):
		Attendance.objects.create(member=self.member)
		token = self._generate_token('gym_management:self_checkin')

		response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.nearby_payload},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn('already checked in', response.context['error_message'])
		self.assertFalse(CheckInSession.objects.get(pk=token).used)

	def test_checkout_without_open_session_is_rejected(self):
		token = self._generate_token('gym_management:self_checkout')

		response = self.client.post(
			reverse('gym_management:self_checkout_confirm'),
			{'token': token, **self.nearby_payload},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.context['error_message'],
			'You do not have an active check-in session to check out from.',
		)
		self.assertFalse(CheckInSession.objects.get(pk=token).used)

	def test_token_reuse_attempt_is_rejected(self):
		token = self._generate_token('gym_management:self_checkin')

		first_response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.nearby_payload},
		)
		self.assertTrue(first_response.context['check_in_success'])

		second_response = self.client.post(
			reverse('gym_management:self_checkin_confirm'),
			{'token': token, **self.nearby_payload},
		)

		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(
			second_response.context['error_message'],
			AttendanceService.INVALID_QR_MESSAGE,
		)
		self.assertEqual(Attendance.objects.filter(member=self.member).count(), 1)

	def test_successful_self_check_out(self):
		attendance = Attendance.objects.create(member=self.member)
		token = self._generate_token('gym_management:self_checkout')

		response = self.client.post(
			reverse('gym_management:self_checkout_confirm'),
			{'token': token, **self.nearby_payload},
		)

		attendance.refresh_from_db()
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['checkout_success'])
		self.assertIsNotNone(attendance.check_out)
		self.assertTrue(CheckInSession.objects.get(pk=token).used)