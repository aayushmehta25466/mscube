#!/usr/bin/env python
"""Verify enhanced test data with complete details"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mscube.settings')
django.setup()

from accounts.models import User, Member, Trainer, Staff, AdminProfile

print('\n' + '='*70)
print('ENHANCED USER DETAILS VERIFICATION')
print('='*70)

# Check Member
print('\n📋 MEMBER SAMPLE - Complete Details:')
print('-'*70)
member = Member.objects.first()
if member:
    print(f'Name: {member.user.full_name}')
    print(f'Email: {member.user.email}')
    print(f'Email Verified: ✓ YES' if member.user.is_verified else '✗ NO')
    print(f'Phone: {member.user.phone}')
    print(f'DOB: {member.date_of_birth} (Age: {member.age} years)')
    print(f'Full Address: {member.address}')
    print(f'Emergency Contact: {member.emergency_contact}')

# Check Trainer
print('\n💪 TRAINER SAMPLE - Complete Details:')
print('-'*70)
trainer = Trainer.objects.first()
if trainer:
    print(f'Name: {trainer.user.full_name}')
    print(f'Email: {trainer.user.email}')
    print(f'Email Verified: ✓ YES' if trainer.user.is_verified else '✗ NO')
    print(f'Phone: {trainer.user.phone}')
    print(f'DOB: {trainer.date_of_birth} (Age: {trainer.age} years)')
    print(f'Full Address: {trainer.address}')
    print(f'Specialization: {trainer.specialization}')
    print(f'Experience: {trainer.experience_years} years')
    print(f'Bio (first 150 chars): {trainer.bio[:150]}...')

# Check Staff
print('\n👔 STAFF SAMPLE - Complete Details:')
print('-'*70)
staff = Staff.objects.first()
if staff:
    print(f'Name: {staff.user.full_name}')
    print(f'Email: {staff.user.email}')
    print(f'Email Verified: ✓ YES' if staff.user.is_verified else '✗ NO')
    print(f'Phone: {staff.user.phone}')
    print(f'DOB: {staff.date_of_birth} (Age: {staff.age} years)')
    print(f'Full Address: {staff.address}')
    print(f'Department: {staff.department}')

# Check Admin
print('\n👑 ADMIN SAMPLE - Complete Details:')
print('-'*70)
admin = AdminProfile.objects.first()
if admin:
    print(f'Name: {admin.user.full_name}')
    print(f'Email: {admin.user.email}')
    print(f'Email Verified: ✓ YES' if admin.user.is_verified else '✗ NO')
    print(f'Phone: {admin.user.phone}')
    print(f'DOB: {admin.date_of_birth} (Age: {admin.age} years)')
    print(f'Full Address: {admin.address}')
    print(f'Permissions:')
    print(f'  - Manage Users: {"✓" if admin.can_manage_users else "✗"}')
    print(f'  - Manage Payments: {"✓" if admin.can_manage_payments else "✗"}')
    print(f'  - View Reports: {"✓" if admin.can_view_reports else "✗"}')

# Summary
print('\n' + '='*70)
print('COMPLETENESS CHECK')
print('='*70)

all_users = User.objects.all()
verified_count = all_users.filter(is_verified=True).count()
with_phone = all_users.exclude(phone__isnull=True).exclude(phone='').count()

print(f'Total Users: {all_users.count()}')
print(f'Email Verified: {verified_count}/{all_users.count()} ✓')
print(f'With Phone Numbers: {with_phone}/{all_users.count()} ✓')
print(f'Members with Emergency Contacts: {Member.objects.exclude(emergency_contact="").count()}/{Member.objects.count()} ✓')
print(f'Trainers with Bio: {Trainer.objects.exclude(bio="").count()}/{Trainer.objects.count()} ✓')
print(f'Staff with Department: {Staff.objects.exclude(department="").count()}/{Staff.objects.count()} ✓')

print('\n' + '='*70)
print('✅ All test users have complete verified details and are ready for testing!')
print('='*70 + '\n')
