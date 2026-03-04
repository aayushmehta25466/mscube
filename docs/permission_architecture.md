# Permission Architecture

## Role Model
Role resolution is profile-based:
- Admin (`adminprofile`)
- Staff (`staff`)
- Trainer (`trainer`)
- Member (`member`)

## Access Principles
- Enforce role checks on every protected endpoint.
- Prefer class-based views with role mixins from `accounts/mixins.py`.
- Prevent IDOR by scoping object queries by authorized visibility.

## Required Mixins
- `AdminRequiredMixin`
- `StaffRequiredMixin`
- `TrainerRequiredMixin`
- `MemberRequiredMixin`
- `StaffOrAdminRequiredMixin`

## Function-Based Views
- FBVs must apply equivalent strict permission gates.
- Do not rely on ad-hoc role checks that bypass centralized policy utilities.
