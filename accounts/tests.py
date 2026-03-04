from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed

from .models import Member

User = get_user_model()


class EmailConfirmationSignalTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			email='signal-user@test.com',
			username='signal_user',
			password='testpass123',
			full_name='Signal User',
			is_verified=False,
		)
		self.email_address = EmailAddress.objects.create(
			user=self.user,
			email=self.user.email,
			primary=True,
			verified=False,
		)

	def test_email_confirmed_signal_creates_member_profile(self):
		email_confirmed.send(
			sender=self.__class__,
			request=None,
			email_address=self.email_address,
		)
		self.user.refresh_from_db()
		self.assertTrue(self.user.is_verified)
		self.assertTrue(Member.objects.filter(user=self.user).exists())

	def test_email_confirmed_signal_is_idempotent(self):
		email_confirmed.send(
			sender=self.__class__,
			request=None,
			email_address=self.email_address,
		)
		email_confirmed.send(
			sender=self.__class__,
			request=None,
			email_address=self.email_address,
		)
		self.assertEqual(Member.objects.filter(user=self.user).count(), 1)


class AuthenticationSurfaceTests(TestCase):
	def test_login_template_has_no_social_login_text(self):
		response = self.client.get(reverse('account_login'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Email or Username')
		self.assertContains(response, 'Password')
		self.assertNotContains(response, 'Google')
		self.assertNotContains(response, 'Facebook')

	def test_social_provider_routes_are_not_available(self):
		self.assertEqual(self.client.get('/accounts/google/login/').status_code, 404)
		self.assertEqual(self.client.get('/accounts/facebook/login/').status_code, 404)

	def test_core_allauth_routes_resolve(self):
		self.assertEqual(self.client.get(reverse('account_signup')).status_code, 200)
		self.assertEqual(self.client.get(reverse('account_login')).status_code, 200)
		self.assertEqual(self.client.get(reverse('account_reset_password')).status_code, 200)
