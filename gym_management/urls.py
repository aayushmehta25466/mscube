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
    assign_subscription_to_member,
    PaymentListView,
    PaymentCreateView,
    PaymentDetailView,
    AttendanceListView,
    AttendanceReportView,
    attendance_checkin,
    attendance_checkout,
    # Member
    MemberDashboardView,
    MySubscriptionView,
    MyAttendanceView,
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
    
    # Payments
    path('payments/', PaymentListView.as_view(), name='payment_list'),
    path('payments/add/', PaymentCreateView.as_view(), name='payment_create'),
    path('payments/<int:pk>/', PaymentDetailView.as_view(), name='payment_detail'),
    
    # Attendance
    path('attendance/', AttendanceListView.as_view(), name='attendance_list'),
    path('attendance/report/', AttendanceReportView.as_view(), name='attendance_report'),
    path('attendance/checkin/', attendance_checkin, name='attendance_checkin'),
    path('attendance/<int:attendance_id>/checkout/', attendance_checkout, name='attendance_checkout'),
    
    # Member Dashboard
    path('my-dashboard/', MemberDashboardView.as_view(), name='member_dashboard'),
    path('my-subscription/', MySubscriptionView.as_view(), name='my_subscription'),
    path('my-attendance/', MyAttendanceView.as_view(), name='my_attendance'),
    
    # Trainer Dashboard
    path('trainer-dashboard/', TrainerDashboardView.as_view(), name='trainer_dashboard'),
    
    # Staff Dashboard
    path('staff-dashboard/', StaffDashboardView.as_view(), name='staff_dashboard'),
]

