# MScube Gym Management - AI Agent Guidelines

## Code Style

**Models** - Follow patterns in [accounts/models.py](../accounts/models.py):
- Use abstract base classes with `%(class)s` for related names ([BaseProfile](../accounts/models.py#L87-L103))
- Implement custom managers for model-specific logic ([UserManager](../accounts/models.py#L7-L38))
- Add `Meta` with `db_table`, `verbose_name`, `ordering`, and database indexes

**Views** - Follow patterns in [gym_management/views.py](../gym_management/views.py):
- Use class-based views (CBVs) exclusively
- Stack mixins: `LoginRequiredMixin` + role mixin (e.g., `AdminRequiredMixin`)
- Override `get_context_data()` for adding template context

**URLs** - See [mscube/urls.py](../mscube/urls.py), [accounts/urls.py](../accounts/urls.py):
- `accounts/` has NO `app_name` namespace (required for django-allauth compatibility)
- Other apps use namespaces: reference as `gym_management:member_list`

## Architecture

**App Structure:**
- **accounts/** - Custom user model, all profiles (Member/Trainer/Staff/Admin), auth mixins
- **gym_management/** - Membership plans, subscriptions, payments, attendance
- **gym_website/** - Public-facing static pages

**Custom User Model** - [accounts/models.py](../accounts/models.py#L41-L79):
```python
AUTH_USER_MODEL = 'accounts.User'
USERNAME_FIELD = 'username'  # Auto-generated from email if not provided
REQUIRED_FIELDS = ['email', 'full_name']
```

**Role System** - NOT using Django groups/permissions:
- Check roles via profile existence: `hasattr(user, 'member')`, `hasattr(user, 'adminprofile')`
- Priority: AdminProfile > Trainer > Staff > Member
- Use utility functions: `get_user_role(user)`, `get_user_profile(user)` from [accounts/utils.py](../accounts/utils.py)

**Signal-Driven Profiles** - [accounts/signals.py](../accounts/signals.py):
- Member profile auto-created ONLY after email verification (`email_confirmed` signal)
- Prevents duplicate profiles - checks if any profile exists before creating
- Signals must be imported in `AccountsConfig.ready()` - see [accounts/apps.py](../accounts/apps.py)

## Build and Test

**Setup:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

**Development:**
```bash
python manage.py runserver                      # Start Django server
npm run dev                                      # Watch Tailwind CSS (in separate terminal)
python manage.py test                           # Run tests (uses Django test framework, not pytest)
python manage.py makemigrations                 # Create migrations
```

**Production:**
```bash
npm run build                                    # Minify CSS
python manage.py collectstatic --no-input       # Gather static files
```

## Project Conventions

**Permission Mixins** - [accounts/mixins.py](../accounts/mixins.py):
```python
# Stack mixins in order: LoginRequiredMixin + RoleMixin
class MemberListView(AdminRequiredMixin, ListView):
    model = Member
```
Available mixins: `AdminRequiredMixin`, `TrainerRequiredMixin`, `StaffRequiredMixin`, `MemberRequiredMixin`, `StaffOrAdminRequiredMixin`

**Admin Permissions** - Granular field-level checks:
```python
from accounts.utils import can_manage_users, can_manage_payments, can_view_reports
if can_manage_users(request.user):
    # Allow user management operations
```

**Dashboard Routing** - Use utility function:
```python
from accounts.utils import get_dashboard_url
redirect_url = get_dashboard_url(request.user)  # Returns role-specific dashboard
```

**Single Active Subscription** - Members can only have ONE active subscription at a time. Check constraint exists at [gym_management/models.py](../gym_management/models.py#L83-L87).

## Integration Points

**Authentication Backend Stack** - [mscube/settings.py](../mscube/settings.py):
1. `django.contrib.auth.backends.ModelBackend` (standard Django)
2. `allauth.account.auth_backends.AuthenticationBackend` (OAuth)
3. `axes.backends.AxesStandaloneBackend` (brute force protection - 5 attempts = 1 hour lockout)

**Allauth Configuration:**
- `ACCOUNT_EMAIL_VERIFICATION = 'mandatory'` - users MUST verify email before system access
- Login methods: username OR email accepted
- Social auth providers configured: Google, Facebook (requires OAuth credentials in settings)

**Database:**
- Default: SQLite (development)
- Production: Set `USE_POSTGRES=True` in environment, configure `DB_*` variables
- Uses `psycopg` 3.x (async-capable PostgreSQL driver)

## Security

**Email Verification Mandatory** - Users cannot access system until email is verified. Member profile creation happens AFTER verification via `email_confirmed` signal.

**Brute Force Protection** - django-axes tracks failed login attempts. After 5 failures, account locked for 1 hour.

**Role-Based Access:**
- Always use permission mixins from [accounts/mixins.py](../accounts/mixins.py) for protected views
- Check profile existence before operations: `if hasattr(request.user, 'adminprofile'):`
- For granular admin permissions, use utility functions: `can_manage_users()`, `can_manage_payments()`, `can_view_reports()`

**Production Settings** - SSL/HSTS configuration present but DEBUG-gated. Ensure `DEBUG=False` and `ALLOWED_HOSTS` configured in production.
