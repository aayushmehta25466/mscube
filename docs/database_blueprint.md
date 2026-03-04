# Database Blueprint

## Primary Domain Models

### accounts app
- `User`
- `Member`
- `Trainer`
- `Staff`
- `AdminProfile`

### gym_management app
- `MembershipPlan`
- `Subscription`
- `Payment`
- `Attendance`

## Core Relationships
- `User` to role profile models: one-to-one
- `Member` to `Subscription`: one-to-many
- `Subscription` to `Payment`: one-to-many
- `Member` to `Attendance`: one-to-many
- `MembershipPlan` to `Subscription`: one-to-many

## Integrity Rules
- Single active subscription per member should be enforced by constraint and workflow checks.
- Financial records should be protected from unsafe deletion behavior.
- Transaction IDs must be non-predictable.
