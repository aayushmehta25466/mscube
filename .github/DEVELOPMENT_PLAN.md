# MScube Gym Management - Development Plan

**Project:** MScube Fitness Center Management System  
**Location:** Inaruwa Municipality-1, Sunsari, Koshi Province, Nepal  
**Technology:** Django 5.x + Tailwind CSS + PostgreSQL  
**Last Updated:** February 17, 2026

---

## Project Overview

A comprehensive gym management system handling member registration, trainer/staff management, membership plans, payment processing, attendance tracking, and administrative operations.

---

## Current Status (Completed)

### ✅ Phase 0: Foundation & Authentication (COMPLETED)

**Infrastructure:**
- Django 5.2.11 project setup with Python 3.14+
- Virtual environment configuration
- Tailwind CSS v4.1.18 integration
- SQLite (dev) / PostgreSQL (production) support
- Environment variable management with python-dotenv

**Authentication System:**
- Custom User model with email + username login
- Email verification mandatory via django-allauth
- OAuth integration (Google, Facebook) ready
- Brute force protection (django-axes) - 5 attempts = 1 hour lockout
- Signal-driven profile creation post email verification

**Profile Management:**
- Member Profile (emergency contact, DOB, address)
- Trainer Profile (specialization, experience, bio)
- Staff Profile (department assignment)
- Admin Profile (granular permissions: users, payments, reports)
- BaseProfile abstract class for common fields

**Core Models:**
- MembershipPlan (flexible pricing, duration, features)
- Subscription (member plan assignments, expiry tracking)
- Payment (multiple methods, eSewa ready, transaction tracking)
- Attendance (check-in/out system, duration calculation)

**Security:**
- Role-based access via profile existence checks
- Permission mixins (AdminRequired, TrainerRequired, etc.)
- Django admin with comprehensive management interfaces
- Production security settings prepared

**Public Website:**
- Home, About, Contact, Programs, Trainers, Events, Tech pages
- Tailwind-based responsive templates

---

## Development Roadmap

### 🚧 Phase 1: User Interface & Dashboard Development (IN PROGRESS)

**Priority:** HIGH  
**Timeline:** 3-4 weeks  
**Status:** 40% Complete

#### 1.1 Authentication Templates ⏳
- [ ] Login page (`templates/accounts/login.html`)
  - Username or email input
  - OAuth buttons (Google, Facebook)
  - Remember me checkbox
  - Password reset link
- [ ] Signup page (`templates/accounts/signup.html`)
  - Full name, email, password fields
  - Email verification notice
  - Terms & conditions checkbox
- [ ] Email verification templates
  - Verification email body
  - Email confirmed success page
  - Resend verification link
- [ ] Password reset flow
  - Request reset page
  - Check email instruction page
  - Password reset form
  - Success confirmation

#### 1.2 Profile Management ⏳
- [x] Profile view template (`templates/accounts/profile.html`)
- [x] Profile update template (`templates/accounts/profile_update.html`)
- [ ] Profile views implementation
  - Display user info and role-specific data
  - Edit profile with image upload
  - Change password functionality
  - Emergency contact management (members)

#### 1.3 Dashboard Views 🔜
- [ ] **Member Dashboard** (`templates/gym_management/member_dashboard.html`)
  - Active subscription details (plan, expiry, days remaining)
  - Attendance history (last 7 days, monthly stats)
  - Payment history
  - Quick check-in button
  - Upcoming events/notifications
  
- [ ] **Trainer Dashboard** (`templates/gym_management/trainer_dashboard.html`)
  - Assigned members list with status
  - Today's schedule
  - Member progress tracking
  - Quick stats (total members, active today)
  
- [ ] **Staff Dashboard** (`templates/gym_management/staff_dashboard.html`)
  - Member check-in/out interface
  - Today's attendance list
  - Active subscriptions overview
  - Quick search member by name/ID
  
- [ ] **Admin Dashboard** (`templates/gym_management/admin_dashboard.html`)
  - Overall statistics (members, revenue, attendance)
  - Recent payments and subscriptions
  - Expiring memberships alert
  - Monthly revenue graph
  - Quick actions (add member, create plan, etc.)

#### 1.4 Member Management Views 🔜
- [x] Member list (`templates/gym_management/member_list.html`)
- [x] Member detail (`templates/gym_management/member_detail.html`)
- [ ] Add new member form
- [ ] Edit member information
- [ ] Assign subscription to member
- [ ] View member attendance history
- [ ] Member subscription renewal

#### 1.5 Attendance Management 🔜
- [x] Attendance list (`templates/gym_management/attendance_list.html`)
- [ ] Check-in interface (staff/reception)
  - QR code scanner option
  - Manual member ID/name search
  - Display member photo and status
- [ ] Check-out interface
- [ ] Attendance reports
  - Daily attendance list
  - Monthly member attendance summary
  - Peak hours analysis

---

### 📋 Phase 2: Business Logic & Operations (PLANNED)

**Priority:** HIGH  
**Timeline:** 4-5 weeks  
**Dependencies:** Phase 1 completion

#### 2.1 Subscription Management 🔜
- [ ] **Create Subscription Workflow**
  - Select member
  - Choose membership plan
  - Set start date (auto-calculate end date)
  - Initialize payment
  - Send confirmation email
  
- [ ] **Subscription Renewal**
  - Renewal form (same plan or upgrade)
  - Early renewal discount logic
  - Auto-extend end date
  - Payment processing
  
- [ ] **Expiry Notifications**
  - Email alerts (7 days, 3 days, 1 day before expiry)
  - Dashboard notification badges
  - SMS integration option (future)
  
- [ ] **Subscription Reports**
  - Active subscriptions count
  - Expiring soon (next 7 days)
  - Cancelled subscriptions analysis
  - Revenue by plan type

#### 2.2 Payment Gateway Integration 🔜
- [ ] **eSewa Payment Integration**
  - Payment initiation view
  - Success callback handler
  - Failure callback handler
  - Transaction verification
  - Automatic payment status update
  
- [ ] **Payment Views**
  - Create payment form
  - Payment history list
  - Payment receipt generation (PDF)
  - Refund processing interface
  
- [ ] **Manual Payment Entry**
  - Cash payment recording
  - Card payment recording
  - Bank transfer recording
  - Receipt number generation

#### 2.3 Membership Plan Management 🔜
- [ ] Create plan form with feature builder
- [ ] Edit plan (with active subscription handling)
- [ ] Deactivate plan
- [ ] Plan comparison view (public)
- [ ] Plan analytics (popularity, revenue)

#### 2.4 Analytics & Reporting 🔜
- [ ] **Revenue Reports**
  - Daily/weekly/monthly revenue
  - Revenue by payment method
  - Revenue by membership plan
  - Projected revenue (active subscriptions)
  
- [ ] **Member Analytics**
  - New members per month
  - Member retention rate
  - Churn analysis
  - Member demographics
  
- [ ] **Attendance Analytics**
  - Peak hours identification
  - Average attendance per day/week
  - Member attendance patterns
  - Inactive member identification
  
- [ ] **Export Features**
  - CSV export for all reports
  - PDF report generation
  - Excel export with charts

#### 2.5 Notification System 🔜
- [ ] Email notifications
  - Welcome email post-verification
  - Subscription activation
  - Payment confirmation
  - Membership expiry warnings
  - Payment reminders
  
- [ ] In-app notifications
  - Dashboard notification center
  - Notification badges
  - Mark as read functionality
  
- [ ] SMS notifications (optional)
  - Payment confirmations
  - Membership expiry alerts
  - OTP for sensitive operations

---

### 🚀 Phase 3: Advanced Features (FUTURE)

**Priority:** MEDIUM  
**Timeline:** 6-8 weeks  
**Dependencies:** Phase 2 completion

#### 3.1 REST API Development 🔮
- [ ] Django REST Framework integration
- [ ] Authentication (JWT tokens)
- [ ] Member endpoints (profile, subscription, attendance)
- [ ] Trainer endpoints (assigned members, schedule)
- [ ] Admin endpoints (full CRUD operations)
- [ ] API documentation (Swagger/ReDoc)
- [ ] Rate limiting and throttling

#### 3.2 Mobile Features 🔮
- [ ] **QR Code System**
  - Generate unique QR code per member
  - QR code on member profile
  - QR code scanner for check-in/out
  - QR code on membership card (printable)
  
- [ ] **Mobile-Responsive Dashboards**
  - Touch-optimized navigation
  - Mobile check-in interface
  - Trainer mobile dashboard
  - Push notifications preparation

#### 3.3 Enhanced Member Experience 🔮
- [ ] **Member Portal**
  - Workout plan assignments (from trainers)
  - Progress tracking (weight, measurements)
  - Exercise library with videos
  - Goal setting and tracking
  
- [ ] **Booking System**
  - Personal training session booking
  - Group class registration
  - Equipment reservation
  - Cancellation management

#### 3.4 Trainer Features 🔮
- [ ] Member assignment system
- [ ] Workout plan builder
- [ ] Progress note recording
- [ ] Schedule management
- [ ] Member communication portal
- [ ] Performance reports

#### 3.5 Multi-Branch Support 🔮
- [ ] Branch model and management
- [ ] Branch-specific staff and members
- [ ] Inter-branch member transfer
- [ ] Branch-level reporting
- [ ] Consolidated admin dashboard
- [ ] Branch-specific plans and pricing

#### 3.6 Communication Platform 🔮
- [ ] Real-time chat (Django Channels)
- [ ] Member-to-trainer messaging
- [ ] Announcement system
- [ ] Event management
- [ ] Newsletter system
- [ ] Feedback and complaint system

---

## Technical Debt & Infrastructure

### 🔧 High Priority
- [ ] **Redis Setup**
  - Configure Redis for caching
  - Enable django-ratelimit
  - Session storage optimization
  
- [ ] **Production Deployment**
  - Set `DEBUG=False`
  - Configure strong `SECRET_KEY`
  - Set `ALLOWED_HOSTS`
  - PostgreSQL database setup
  - SMTP email configuration (Gmail)
  - SSL certificate installation
  - Static files serving (Whitenoise or Nginx)
  
- [ ] **Testing Suite**
  - Unit tests for models
  - View tests with authentication
  - Integration tests for workflows
  - Test fixtures for sample data
  - CI/CD pipeline setup

### 🔧 Medium Priority
- [ ] **Performance Optimization**
  - Database query optimization
  - Select_related and prefetch_related
  - Database indexing review
  - Lazy loading for images
  - Frontend asset minification
  
- [ ] **Code Quality**
  - Add type hints (Python 3.14+ support)
  - Code coverage > 80%
  - Pylint/Black/isort setup
  - Pre-commit hooks
  - Documentation improvements

### 🔧 Low Priority
- [ ] Logging configuration (structured logging)
- [ ] Error tracking (Sentry integration)
- [ ] Admin action audit logs
- [ ] Database backup automation
- [ ] Load testing and capacity planning

---

## Security Enhancements

### 🔐 Planned Security Features
- [ ] Two-factor authentication (2FA)
- [ ] Password expiry policy
- [ ] Session timeout configuration
- [ ] IP whitelist for admin access
- [ ] File upload validation
- [ ] CAPTCHA for public forms
- [ ] Content Security Policy (CSP) headers
- [ ] Regular security audit schedule

---

## Integration Roadmap

### Payment Gateways
- [x] eSewa (models ready)
- [ ] eSewa views implementation
- [ ] Khalti integration
- [ ] PayPal integration (international)
- [ ] Stripe integration (international)

### Third-Party Services
- [ ] SMS Gateway (Sparrow SMS, aakash SMS)
- [ ] Email service (SendGrid/Mailgun)
- [ ] Cloud storage (AWS S3 for media files)
- [ ] Google Analytics
- [ ] Social media integration

---

## Testing Strategy

### Unit Tests (Priority: HIGH)
- [ ] accounts/tests.py - User model, profile creation
- [ ] gym_management/tests.py - Subscription logic, payment processing
- [ ] Test signal handlers
- [ ] Test utility functions
- [ ] Test permission mixins

### Integration Tests (Priority: MEDIUM)
- [ ] User registration flow
- [ ] Subscription creation workflow
- [ ] Payment processing end-to-end
- [ ] Attendance check-in/out flow

### UI Tests (Priority: LOW)
- [ ] Selenium tests for critical paths
- [ ] Dashboard functionality
- [ ] Form validations

---

## Documentation Todo

- [ ] API documentation (when REST API implemented)
- [ ] Deployment guide
- [ ] User manual (admin, trainer, member)
- [ ] Code architecture document
- [ ] Database schema documentation
- [ ] Contribution guidelines
- [ ] Security best practices guide

---

## Success Metrics

### Phase 1 Goals
- All authentication flows functional
- All 4 dashboard types operational
- Member and attendance management complete

### Phase 2 Goals
- Payment gateway 100% functional
- Automated subscription renewal working
- Complete reporting suite

### Phase 3 Goals
- Mobile app or PWA launched
- Multi-branch operational
- API publicly available

### Performance Targets
- Page load time < 2 seconds
- 500+ concurrent users support
- 99.9% uptime
- API response time < 200ms

---

## Risk Management

| Risk | Impact | Mitigation |
|------|--------|------------|
| Payment gateway failure | HIGH | Multiple gateway options, retry logic |
| Database scalability | MEDIUM | PostgreSQL with proper indexing, caching |
| Security breach | HIGH | Regular audits, penetration testing |
| Third-party service downtime | MEDIUM | Graceful degradation, local fallbacks |
| Data loss | HIGH | Automated daily backups, redundancy |

---

## Team & Resources

### Required Roles
- [ ] Backend Developer (Django)
- [ ] Frontend Developer (Tailwind/JavaScript)
- [ ] UI/UX Designer
- [ ] QA Tester
- [ ] DevOps Engineer (deployment phase)

### Learning Resources
- Django Documentation: https://docs.djangoproject.com/
- django-allauth: https://django-allauth.readthedocs.io/
- Tailwind CSS: https://tailwindcss.com/docs
- eSewa API: https://developer.esewa.com.np/

---

## Release Schedule

### Version 0.1 (MVP) - Target: 4 weeks
- Authentication + basic dashboards
- Member management
- Basic attendance tracking

### Version 0.2 - Target: 8 weeks  
- Payment processing
- Subscription management
- Email notifications

### Version 0.3 - Target: 12 weeks
- Complete reporting
- Analytics dashboard
- QR code check-in

### Version 1.0 (Production) - Target: 16 weeks
- All Phase 1 & 2 features
- Production ready
- Full test coverage

---

## Contact & Support

**Project Owner:** MScube Fitness Center  
**Email:** mscubefitness@gmail.com  
**Phone:** 9862361278, 9842124920  
**Location:** Inaruwa-1, Sunsari, Koshi Province, Nepal

---

**Note:** This development plan is a living document. Update as priorities shift and new requirements emerge.
