from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    """Custom allauth adapter for role-aware login redirects."""

    def get_login_redirect_url(self, request):
        from .utils import get_dashboard_url

        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            dashboard_url = get_dashboard_url(user)
            if dashboard_url:
                return dashboard_url

        return reverse('accounts_dashboard_redirect')
