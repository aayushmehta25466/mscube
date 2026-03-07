from django.urls import path
from .views import (
    # Admin
    AdminDashboardView,
    MemberListView,
    MemberDetailView,
    MemberCreateView,
    MemberUpdateView,
    MemberDeleteView,
    MembershipPlanListView,
    MembershipPlanCreateView,
    MembershipPlanUpdateView,
    MembershipPlanDeleteView,
    SubscriptionListView,
    SubscriptionCreateView,
    SubscriptionUpdateView,
    SubscriptionCancelView,
    SubscriptionUpgradeView,
    assign_subscription_to_member,
    process_subscription_upgrade,
    PaymentListView,
    PaymentCreateView,
    PaymentDetailView,
    PaymentReceiptView,
    AttendanceListView,
    AttendanceReportView,
    AttendanceQRView,
    attendance_checkin,
    attendance_checkout,
    # Phase 2: eSewa
    EsewaPaymentInitiateView,
    esewa_success_callback,
    esewa_failure_callback,
    # Phase 2: Analytics
    RevenueReportView,
    MembershipAnalyticsView,
    AttendanceAnalyticsView,
    InactiveMembersReportView,
    # Phase 2: Exports
    export_payments_csv,
    export_members_csv,
    export_attendance_csv,
    export_revenue_csv,
    # Phase 2: Notifications
    NotificationListView,
    mark_notification_read,
    mark_all_notifications_read,
    run_expiry_notifications,
    # Member
    MemberDashboardView,
    MySubscriptionView,
    MyAttendanceView,
    MyPaymentsView,
    # Phase 3: QR Self Check-In/Out
    SelfCheckInView,
    SelfCheckInConfirmView,
    SelfCheckOutView,
    SelfCheckOutConfirmView,
    # Trainer
    TrainerDashboardView,
    # Staff
    StaffDashboardView,
)

app_name = 'gym_management'

urlpatterns = [
    # Admin Dashboard
    path('', AdminDashboardView.as_view(), name='admin_dashboard'),
    
    # Member Management
    path('members/', MemberListView.as_view(), name='member_list'),
    path('members/add/', MemberCreateView.as_view(), name='member_create'),
    path('members/<int:pk>/', MemberDetailView.as_view(), name='member_detail'),
    path('members/<int:pk>/edit/', MemberUpdateView.as_view(), name='member_update'),
    path('members/<int:pk>/delete/', MemberDeleteView.as_view(), name='member_delete'),
    path('members/<int:member_id>/assign-subscription/', assign_subscription_to_member, name='assign_subscription'),
    
    # Membership Plans
    path('plans/', MembershipPlanListView.as_view(), name='plan_list'),
    path('plans/add/', MembershipPlanCreateView.as_view(), name='plan_create'),
    path('plans/<int:pk>/edit/', MembershipPlanUpdateView.as_view(), name='plan_update'),
    path('plans/<int:pk>/delete/', MembershipPlanDeleteView.as_view(), name='plan_delete'),
    
    # Subscriptions
    path('subscriptions/', SubscriptionListView.as_view(), name='subscription_list'),
    path('subscriptions/add/', SubscriptionCreateView.as_view(), name='subscription_create'),
    path('subscriptions/<int:pk>/edit/', SubscriptionUpdateView.as_view(), name='subscription_update'),
    path('subscriptions/<int:pk>/cancel/', SubscriptionCancelView.as_view(), name='subscription_cancel'),
    path('subscriptions/<int:pk>/upgrade/', SubscriptionUpgradeView.as_view(), name='subscription_upgrade'),
    path('subscriptions/<int:pk>/process-upgrade/', process_subscription_upgrade, name='process_subscription_upgrade'),
    
    # Payments
    path('payments/', PaymentListView.as_view(), name='payment_list'),
    path('payments/add/', PaymentCreateView.as_view(), name='payment_create'),
    path('payments/<int:pk>/', PaymentDetailView.as_view(), name='payment_detail'),
    path('payments/<int:pk>/receipt/', PaymentReceiptView.as_view(), name='payment_receipt'),
    
    # eSewa Payment Gateway
    path('payments/<int:payment_id>/esewa/', EsewaPaymentInitiateView.as_view(), name='esewa_initiate'),
    path('payments/esewa/success/', esewa_success_callback, name='esewa_success'),
    path('payments/esewa/failure/', esewa_failure_callback, name='esewa_failure'),
    
    # Attendance
    path('attendance/', AttendanceListView.as_view(), name='attendance_list'),
    path('attendance/qr/', AttendanceQRView.as_view(), name='attendance_qr'),
    path('attendance/report/', AttendanceReportView.as_view(), name='attendance_report'),
    path('attendance/checkin/', attendance_checkin, name='attendance_checkin'),
    path('attendance/<int:attendance_id>/checkout/', attendance_checkout, name='attendance_checkout'),
    
    # Analytics & Reports
    path('reports/revenue/', RevenueReportView.as_view(), name='revenue_report'),
    path('reports/membership/', MembershipAnalyticsView.as_view(), name='membership_analytics'),
    path('reports/attendance/', AttendanceAnalyticsView.as_view(), name='attendance_analytics'),
    path('reports/inactive-members/', InactiveMembersReportView.as_view(), name='inactive_members_report'),
    
    # Exports
    path('export/payments/', export_payments_csv, name='export_payments'),
    path('export/members/', export_members_csv, name='export_members'),
    path('export/attendance/', export_attendance_csv, name='export_attendance'),
    path('export/revenue/', export_revenue_csv, name='export_revenue'),
    
    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/read/', mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Admin utilities
    path('admin/run-expiry-notifications/', run_expiry_notifications, name='run_expiry_notifications'),
    
    # Member Dashboard
    path('my-dashboard/', MemberDashboardView.as_view(), name='member_dashboard'),
    path('my-subscription/', MySubscriptionView.as_view(), name='my_subscription'),
    path('my-attendance/', MyAttendanceView.as_view(), name='my_attendance'),
    path('my-payments/', MyPaymentsView.as_view(), name='my_payments'),
    
    # Phase 3: QR Self Check-In/Out
    path('self-checkin/', SelfCheckInView.as_view(), name='self_checkin'),
    path('self-checkin/confirm/', SelfCheckInConfirmView.as_view(), name='self_checkin_confirm'),
    path('self-checkout/', SelfCheckOutView.as_view(), name='self_checkout'),
    path('self-checkout/confirm/', SelfCheckOutConfirmView.as_view(), name='self_checkout_confirm'),
    
    # Trainer Dashboard
    path('trainer-dashboard/', TrainerDashboardView.as_view(), name='trainer_dashboard'),
    
    # Staff Dashboard
    path('staff-dashboard/', StaffDashboardView.as_view(), name='staff_dashboard'),
]

