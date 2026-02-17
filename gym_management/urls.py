from django.urls import path
from .views import (
    # Admin
    AdminDashboardView,
    MemberListView,
    MemberDetailView,
    MembershipPlanListView,
    SubscriptionListView,
    PaymentListView,
    AttendanceListView,
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
    path('members/<int:pk>/', MemberDetailView.as_view(), name='member_detail'),
    
    # Membership Plans
    path('plans/', MembershipPlanListView.as_view(), name='plan_list'),
    
    # Subscriptions
    path('subscriptions/', SubscriptionListView.as_view(), name='subscription_list'),
    
    # Payments
    path('payments/', PaymentListView.as_view(), name='payment_list'),
    
    # Attendance
    path('attendance/', AttendanceListView.as_view(), name='attendance_list'),
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

