# MScube Gym Management System

A comprehensive gym management system built with Django 5.x, featuring custom authentication, role-based access control, membership management, payment processing, and attendance tracking.

## Features

### Authentication & User Management
- ✅ **Custom User Model** with email and username login
- ✅ **Email Verification** (configurable: mandatory/optional/none via environment)
- ✅ **OAuth Integration** (Google & Facebook via django-allauth)
- ✅ **Role-Based Access Control** (Member, Trainer, Staff, Admin)
- ✅ **Brute Force Protection** (django-axes)
- ✅ **Profile Auto-Creation** via signals

### Profile System
- ✅ **Member Profile** - Emergency contact, personal info
- ✅ **Trainer Profile** - Specialization, experience, bio
- ✅ **Staff Profile** - Department assignment
- ✅ **Admin Profile** - Granular permissions (manage users, payments, reports)

### Gym Management
- ✅ **Membership Plans** - Flexible pricing and duration
- ✅ **Subscriptions** - Member plan assignments with expiry tracking
- ✅ **Payment Processing** - Cash, card, online, eSewa integration ready
- ✅ **Attendance Tracking** - Check-in/check-out system with duration calculation

## Technology Stack

- **Framework:** Django 5.2.11 (Python 3.14+)
- **Database:** SQLite (dev) / PostgreSQL (production)
- **Authentication:** django-allauth 65.14.3
- **Frontend:** Tailwind CSS v4.1.18
- **Security:** django-axes (login attempt tracking)

## Architecture

```
mscube/
├── accounts/           # User authentication & profiles
│   ├── models.py      # Custom User, Member, Trainer, Staff, AdminProfile
│   ├── signals.py     # Auto-create Member profile on email verification
│   ├── mixins.py      # Permission mixins (AdminRequired, MemberRequired, etc.)
│   └── utils.py       # Helper functions (get_user_role, get_dashboard_url)
│
├── gym_management/    # Core gym operations
│   ├── models.py      # MembershipPlan, Subscription, Payment, Attendance
│   └── admin.py       # Comprehensive Django admin
│
├── gym_website/       # Public-facing website
│   ├── views.py       # Static pages (home, about, contact, etc.)
│   └── templates/     # Modern Tailwind-based templates
│
└── mscube/            # Project settings
    ├── settings.py    # Configuration with allauth, axes, email
    └── urls.py        # URL routing
```

## Setup Instructions

### 1. Clone and Setup Virtual Environment

```bash
cd /path/to/mscube
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
cp .env.example .env
# Edit .env and set your SECRET_KEY and other settings
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
# You'll be prompted for: username, email, full_name, password
```

### 6. Run Development Server

```bash
python manage.py runserver
```

Visit:
- **Public Website:** http://localhost:8000/
- **Django Admin:** http://localhost:8000/admin/
- **Account Management:** http://localhost:8000/accounts/

## User Roles & Permissions

### Public Signup Flow
1. User registers at `/accounts/signup/`
2. Verification behavior follows environment config (mandatory, optional, or none)
3. If verification is mandatory/optional, allauth sends verification email
4. **Member profile automatically created** via signal after email confirmation
5. User can login and access role-appropriate dashboard

### Role Hierarchy

| Role | Profile Model | Access Level | Auto-Created |
|------|--------------|--------------|--------------|
| **Member** | `Member` | My dashboard, attendance, subscriptions | ✅ Yes (on email verification) |
| **Trainer** | `Trainer` | Trainer dashboard, assigned members | ❌ Admin creates |
| **Staff** | `Staff` | Staff dashboard, check-in/out members | ❌ Admin creates |
| **Admin** | `AdminProfile` | Full management access | ❌ Admin creates |

### Permission Mixins

Use in views to restrict access:

```python
from accounts.mixins import AdminRequiredMixin, MemberRequiredMixin

class MemberDashboardView(MemberRequiredMixin, TemplateView):
    template_name = 'member_dashboard.html'

class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = 'admin_dashboard.html'
```

### Utility Functions

```python
from accounts.utils import get_user_role, get_user_profile, user_has_permission

# Get user's role
role = get_user_role(request.user)  # Returns: 'admin', 'trainer', 'staff', 'member', or None

# Get user's profile instance
profile = get_user_profile(request.user)

# Check admin permissions
if user_has_permission(request.user, 'can_manage_users'):
    # Allow user management

# Quick role checks
from accounts.utils import is_admin, is_member
if is_admin(request.user):
    # Admin-specific logic
```

## Database Models

### Custom User Model
```python
User:
- username (unique, auto-generated from email if not provided)
- email (unique, required)
- full_name (required)
- phone (optional)
- is_verified (email verification status)
```

### Profile Models
```python
Member:
- user (OneToOne → User)
- date_of_birth, address
- emergency_contact
- age (calculated property)

Trainer:
- user (OneToOne → User)
- specialization, experience_years, bio
- date_of_birth, address

Staff:
- user (OneToOne → User)
- department
- date_of_birth, address

AdminProfile:
- user (OneToOne → User)
- access_level (full/limited)
- can_manage_users, can_manage_payments, can_view_reports
```

### Gym Management Models
```python
MembershipPlan:
- name, description, price, duration_days
- features (text/JSON)
- is_active

Subscription:
- member (FK → Member)
- plan (FK → MembershipPlan)
- start_date, end_date
- status (pending/active/expired/cancelled)
- Constraint: Only ONE active subscription per member

Payment:
- subscription (FK → Subscription)
- amount, payment_method, status
- transaction_id (auto-generated)
- esewa_transaction_code, esewa_ref_id
- Methods: mark_completed(), mark_failed()

Attendance:
- member (FK → Member)
- check_in, check_out (nullable)
- date (for queries)
- Methods: duration(), checkout()
```

## Django Admin Features

### User Management
- View all users with verification status
- Filter by role, staff status, verification
- Inline profile display

### Subscription Management
- Colored status badges (active=green, pending=orange, expired=red)
- Bulk actions: Activate, Cancel, Check Expired
- Days remaining calculation

### Payment Tracking
- Transaction ID auto-generation
- Status tracking with colored badges
- Bulk mark as completed/failed
- eSewa integration fields

### Attendance Reports
- Date hierarchy navigation
- Duration calculation
- Member search and filtering

## Email Verification

### Environment Controls
Use these environment variables to control verification policy without code changes:

```env
# Allowed: mandatory | optional | none
ACCOUNT_EMAIL_VERIFICATION_MODE=mandatory

# true => email required at signup, false => email optional
ACCOUNT_EMAIL_REQUIRED=True
```

- ACCOUNT_EMAIL_VERIFICATION_MODE=mandatory: Email confirmation required before account is treated as verified
- ACCOUNT_EMAIL_VERIFICATION_MODE=optional: Signup allowed; verification email can still be sent
- ACCOUNT_EMAIL_VERIFICATION_MODE=none: No verification flow enforced

For local auth-workflow testing, a typical setup is:

```env
ACCOUNT_EMAIL_VERIFICATION_MODE=optional
ACCOUNT_EMAIL_REQUIRED=True
```

### Development
Emails are printed to console (check terminal output)

### Production
Configure SMTP in `.env`:
```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

For Gmail, use [App Passwords](https://support.google.com/accounts/answer/185833)

## OAuth Setup

### Google OAuth
1. Create project at [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google+ API
3. Create OAuth 2.0 credentials
4. Add to Django admin: **Sites > Add** (domain: localhost:8000)
5. Add to Django admin: **Social Applications > Add Google**
   - Client ID: from Google Console
   - Secret key: from Google Console
   - Sites: Select your site

### Facebook OAuth
1. Create app at [Facebook Developers](https://developers.facebook.com/)
2. Get App ID and App Secret
3. Add to Django admin: **Social Applications > Add Facebook**

## Payment Integration (eSewa)

eSewa integration is ready for implementation. To enable:

1. Get merchant credentials from [eSewa](https://esewa.com.np/)
2. Add to `.env`:
```env
ESEWA_MERCHANT_ID=your-merchant-id
ESEWA_SUCCESS_URL=http://yourdomain.com/management/payment/success/
ESEWA_FAILURE_URL=http://yourdomain.com/management/payment/failure/
```
3. Implement views in `gym_management/views.py` (TODO)

## Security Features

### Implemented
- ✅ Custom User model with email verification
- ✅ Login attempt tracking (django-axes)
- ✅ Rate limiting configuration ready
- ✅ CSRF protection enabled
- ✅ Password validators (similarity, length, common, numeric)
- ✅ Production security settings (HTTPS, secure cookies)

### Production Checklist
- [ ] Set `DEBUG=False`
- [ ] Set strong `SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Use PostgreSQL database
- [ ] Configure real SMTP email backend
- [ ] Enable HTTPS (SSL certificates)
- [ ] Set up Redis for caching (django-ratelimit)
- [ ] Configure static files serving (Whitenoise/Nginx)

## Next Steps (TODO)

### Phase 1: Views & Templates
- [ ] Create authentication templates (login, signup, profile)
- [ ] Create admin dashboard views
- [ ] Create member dashboard views
- [ ] Create trainer/staff dashboard views
- [ ] Integrate with existing Tailwind-based templates

### Phase 2: Business Logic
- [ ] Implement subscription renewal workflow
- [ ] Add payment gateway views (eSewa)
- [ ] Create attendance check-in/out interface
- [ ] Add membership expiry notifications
- [ ] Build analytics/reporting dashboard

### Phase 3: Advanced Features
- [ ] QR code generation for member cards
- [ ] Mobile-responsive dashboards
- [ ] REST API (Django REST Framework)
- [ ] Real-time notifications
- [ ] Multi-branch support

## Development Commands

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run server
python manage.py runserver

# Check for issues
python manage.py check

# Production deployment check
python manage.py check --deploy

# Collect static files
python manage.py collectstatic
```

## Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test accounts
python manage.py test gym_management
```

## Project Information

- **Location:** Inaruwa Municipality-1, Sunsari, Koshi Province, Nepal
- **Contact:** 9862361278, 9842124920
- **Email:** mscubefitness@gmail.com
- **Hours:** 5:00 AM - 9:00 PM (Sunday - Friday)
- **Established:** 2026

## License

Proprietary - MScube Fitness Center

## Support

For issues or questions, contact: mscubefitness@gmail.com
