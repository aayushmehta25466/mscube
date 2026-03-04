# MScube Fitness Center Management System

Stack:
- Django 5.x
- PostgreSQL
- Tailwind CSS v4.1
- django-allauth (email verified)
- django-axes brute force protection

Architecture:
- Custom User model
- Role-based profile detection
- Permission mixins (AdminRequired, TrainerRequired)
- Monolith with future multi-branch support

Security:
- CSRF enforced
- Role-based view restrictions
- Payment callbacks must be verified

Current Phase:
Phase 1 – Dashboards + Attendance + Member Management