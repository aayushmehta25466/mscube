from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
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


@override_settings(
    ACCOUNT_EMAIL_VERIFICATION='mandatory',
    ACCOUNT_EMAIL_VERIFICATION_MODE='mandatory',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EndToEndSignupConfirmLoginTest(TestCase):
	"""
	End-to-end lifecycle: signup → email confirmation → login.

	Email delivery is simulated using EmailConfirmationHMAC to produce a
	valid confirmation key without relying on a real SMTP server.  This tests
	the full allauth verification gate flow:
	  1. User signs up — account exists but is unverified.
	  2. Confirmation token is generated (simulating the emailed link).
	  3. Confirmation URL is POSTed — account is verified.
	  4. Member profile is created via the email_confirmed signal.
	  5. User can now log in successfully.
	"""

	def setUp(self):
		# Create user directly (bypass signup form to isolate the confirmation
		# and login steps from form validation complexity).
		self.email = 'e2e-lifecycle@test.com'
		self.password = 'SecureTestPass99!'
		self.user = User.objects.create_user(
			email=self.email,
			username='e2e_lifecycle',
			password=self.password,
			full_name='E2E Lifecycle',
			is_verified=False,
		)
		self.email_address = EmailAddress.objects.create(
			user=self.user,
			email=self.email,
			primary=True,
			verified=False,
		)

	def _get_confirmation_key(self):
		"""Return a valid HMAC confirmation key without sending real email."""
		return EmailConfirmationHMAC(self.email_address).key

	def test_unverified_user_cannot_login(self):
		"""Before confirmation: login should not authenticate the user."""
		response = self.client.post(
			reverse('account_login'),
			{'login': self.email, 'password': self.password},
			follow=True,
		)
		self.assertFalse(response.wsgi_request.user.is_authenticated)

	def test_confirmation_url_verifies_account(self):
		"""After following the confirmation URL the EmailAddress becomes verified."""
		key = self._get_confirmation_key()
		confirm_url = reverse('account_confirm_email', args=[key])
		response = self.client.post(confirm_url, follow=True)
		self.assertEqual(response.status_code, 200)

		self.email_address.refresh_from_db()
		self.assertTrue(self.email_address.verified)

	def test_confirmation_triggers_member_profile_creation(self):
		"""
		The email_confirmed signal creates a Member profile for the user.
		Here we fire the signal directly, as done in the signal unit tests,
		to verify the signal integration in isolation.
		"""
		email_confirmed.send(
			sender=self.__class__,
			request=None,
			email_address=self.email_address,
		)
		self.user.refresh_from_db()
		self.assertTrue(self.user.is_verified)
		self.assertTrue(Member.objects.filter(user=self.user).exists())

	def test_verified_user_can_login(self):
		"""Full lifecycle: confirm email then login succeeds."""
		# Step 1 — confirm email via HMAC token
		key = self._get_confirmation_key()
		confirm_url = reverse('account_confirm_email', args=[key])
		self.client.post(confirm_url, follow=True)

		self.email_address.refresh_from_db()
		self.assertTrue(self.email_address.verified, 'Email should be verified after confirmation')

		# Step 2 — login should now succeed
		response = self.client.post(
			reverse('account_login'),
			{'login': self.email, 'password': self.password},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(
			response.wsgi_request.user.is_authenticated,
			'User should be authenticated after email verification and login',
		)
