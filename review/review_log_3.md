# REVIEW LOG 03

## 📊 Phase 0 Compliance Status

### 2026-03-06 Phase 2 Code Review
- Status: ⚠ Partial (carryover)
- Scope note: Phase 0 controls were not re-validated in this Phase 2 review.

## 📊 Phase 1 Compliance Status

### 2026-03-06 Phase 2 Code Review
- Status: ⚠ Partial (carryover)
- Scope note: Phase 1 controls were not re-validated in this Phase 2 review.

## ⚠ Missing or Partial Implementations

### 2026-03-06 Findings
- Payment and subscription delete protections are not enforced at the model or admin layer; financial records remain deletable via ORM/admin.
- Notification mark-read endpoints rely on request.user.member without MemberRequired checks, causing permission ambiguity and 500s for non-member roles.
- eSewa upgrade payments can fail validation because prorated upgrade amounts are not equal to plan price.

## 🔄 Schema Drift Check

### 2026-03-06 Findings
- No schema drift detected for Phase 2 entities; Notification model and indexes remain consistent with migrations.

## ⚡ Query Optimization Check

### 2026-03-06 Findings
- Expiry notification processing performs per-subscription duplicate checks, introducing an N+1 query pattern.

## 🧪 Test Coverage Gap Analysis

### 2026-03-06 Findings
- No Phase 2 tests were executed for this review.
- Missing targeted tests for eSewa upgrade proration, notification permission gating, and delete-protection enforcement.

## 🚦 Implementation Verdict

### 2026-03-06
- Verdict: ⚠ Partial
- Merge readiness: Phase 2 needs fixes for delete protection, upgrade payment validation, and notification permission gating before production sign-off.


---

## Soft Delete Mechanism Found?

YES (partial)

---

## Current Implementation Details
- Member inherits BaseProfile with an is_active flag; BaseProfile is abstract and does not define deleted_at or similar timestamps.
- User extends AbstractUser and only adds is_verified; no explicit soft delete fields are defined on the model.
- Subscription -> Member uses PROTECT and Payment -> Subscription uses PROTECT; Attendance -> Member uses CASCADE.
- No custom manager or queryset enforces automatic filtering of inactive members.

---

## Problems Found
- Soft delete relies only on an is_active flag with no deletion timestamp or default manager filtering, so hard deletes are still possible.
- Attendance uses CASCADE, so deleting a member without subscriptions can erase attendance history.
- Inactive members are not globally filtered; each query must enforce is_active manually.

---

## Recommendation
2️⃣ Soft delete partially implemented (needs fixes) — is_active exists on Member, but there is no deletion timestamp, no default manager filter, and Attendance cascade can still purge history.
