from django.urls import path, include
from .views import (
    ProfileView,
    ProfileUpdateView,
    dashboard_redirect,
    CustomLoginView,
    CustomSignupView,
    CustomPasswordResetView,
)

# Note: No app_name here because allauth URLs need to be at root level without namespace

urlpatterns = [
    # Custom auth templates
    path('login/', CustomLoginView.as_view(), name='account_login'),
    path('signup/', CustomSignupView.as_view(), name='account_signup'),
    path('password/reset/', CustomPasswordResetView.as_view(), name='account_reset_password'),

    # Custom profile views
    path('profile/', ProfileView.as_view(), name='accounts_profile'),
    path('profile/update/', ProfileUpdateView.as_view(), name='accounts_profile_update'),
    path('dashboard/', dashboard_redirect, name='accounts_dashboard_redirect'),
    
    # Django-allauth URLs (signup, login, logout, password reset, email verification)
    path('', include('allauth.urls')),
]

