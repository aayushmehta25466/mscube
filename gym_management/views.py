from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import date, timedelta
from accounts.mixins import AdminRequiredMixin, TrainerRequiredMixin, StaffRequiredMixin, MemberRequiredMixin, StaffOrAdminRequiredMixin
from accounts.models import Member, Trainer, Staff, User
from .models import MembershipPlan, Subscription, Payment, Attendance


# ==================== ADMIN DASHBOARD ====================

class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """Admin dashboard with overview statistics."""
    template_name = 'gym_management/admin_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistics
        context['total_members'] = Member.objects.filter(is_active=True).count()
        context['active_subscriptions'] = Subscription.objects.filter(status='active').count()
        context['total_trainers'] = Trainer.objects.filter(is_active=True).count()
        context['total_staff'] = Staff.objects.filter(is_active=True).count()
        
        # Revenue this month
        today = date.today()
        first_day = today.replace(day=1)
        context['revenue_this_month'] = Payment.objects.filter(
            status='completed',
            completed_at__gte=first_day
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Today's attendance
        context['attendance_today'] = Attendance.objects.filter(date=today).count()
        
        # Recent activities
        context['recent_subscriptions'] = Subscription.objects.select_related('member__user', 'plan').order_by('-created_at')[:5]
        context['recent_payments'] = Payment.objects.select_related('subscription__member__user').order_by('-initiated_at')[:5]
        context['recent_attendance'] = Attendance.objects.select_related('member__user').order_by('-check_in')[:10]
        
        # Expiring subscriptions (next 7 days)
        next_week = today + timedelta(days=7)
        context['expiring_soon'] = Subscription.objects.filter(
            status='active',
            end_date__gte=today,
            end_date__lte=next_week
        ).select_related('member__user', 'plan').order_by('end_date')
        
        return context


# ==================== MEMBER MANAGEMENT ====================

class MemberListView(AdminRequiredMixin, ListView):
    """List all members with search and filter."""
    model = Member
    template_name = 'gym_management/member_list.html'
    context_object_name = 'members'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Member.objects.select_related('user').filter(is_active=True)
        
        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__full_name__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__phone__icontains=search)
            )
        
        # Filter by subscription status
        status = self.request.GET.get('status')
        if status:
            if status == 'active':
                queryset = queryset.filter(subscriptions__status='active')
            elif status == 'expired':
                queryset = queryset.filter(subscriptions__status='expired')
            elif status == 'no_subscription':
                queryset = queryset.exclude(subscriptions__isnull=False)
        
        return queryset.distinct()


class MemberDetailView(AdminRequiredMixin, DetailView):
    """Detailed view of a member with subscriptions, payments, and attendance."""
    model = Member
    template_name = 'gym_management/member_detail.html'
    context_object_name = 'member'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.get_object()
        
        context['subscriptions'] = member.subscriptions.select_related('plan').order_by('-created_at')
        context['payments'] = Payment.objects.filter(
            subscription__member=member
        ).select_related('subscription__plan').order_by('-initiated_at')[:10]
        context['attendance_records'] = member.attendance_records.order_by('-check_in')[:20]
        
        # Current subscription
        context['current_subscription'] = member.subscriptions.filter(status='active').first()
        
        return context


# ==================== MEMBERSHIP PLANS ====================

class MembershipPlanListView(AdminRequiredMixin, ListView):
    """List all membership plans."""
    model = MembershipPlan
    template_name = 'gym_management/plan_list.html'
    context_object_name = 'plans'
    
    def get_queryset(self):
        return MembershipPlan.objects.all().order_by('price')


# ==================== SUBSCRIPTIONS ====================

class SubscriptionListView(AdminRequiredMixin, ListView):
    """List all subscriptions with filters."""
    model = Subscription
    template_name = 'gym_management/subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Subscription.objects.select_related('member__user', 'plan').all()
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.order_by('-created_at')


# ==================== PAYMENTS ====================

class PaymentListView(AdminRequiredMixin, ListView):
    """List all payments with filters."""
    model = Payment
    template_name = 'gym_management/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Payment.objects.select_related('subscription__member__user', 'subscription__plan').all()
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by payment method
        method = self.request.GET.get('method')
        if method:
            queryset = queryset.filter(payment_method=method)
        
        return queryset.order_by('-initiated_at')


# ==================== ATTENDANCE ====================

class AttendanceListView(StaffOrAdminRequiredMixin, ListView):
    """List attendance records with date filters."""
    model = Attendance
    template_name = 'gym_management/attendance_list.html'
    context_object_name = 'attendance_records'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = Attendance.objects.select_related('member__user').all()
        
        # Filter by date
        date_str = self.request.GET.get('date')
        if date_str:
            try:
                filter_date = date.fromisoformat(date_str)
                queryset = queryset.filter(date=filter_date)
            except ValueError:
                pass
        else:
            # Default to today
            queryset = queryset.filter(date=date.today())
        
        return queryset.order_by('-check_in')


@login_required
def attendance_checkin(request):
    """Check in a member."""
    if not (hasattr(request.user, 'staff') or hasattr(request.user, 'adminprofile')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('/')
    
    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        try:
            member = Member.objects.get(id=member_id, is_active=True)
            
            # Check if already checked in today
            today = date.today()
            existing = Attendance.objects.filter(
                member=member,
                date=today,
                check_out__isnull=True
            ).first()
            
            if existing:
                messages.warning(request, f'{member.user.full_name} is already checked in.')
            else:
                Attendance.objects.create(member=member)
                messages.success(request, f'{member.user.full_name} checked in successfully!')
        except Member.DoesNotExist:
            messages.error(request, 'Member not found.')
    
    return redirect('gym_management:attendance_list')


@login_required
def attendance_checkout(request, attendance_id):
    """Check out a member."""
    if not (hasattr(request.user, 'staff') or hasattr(request.user, 'adminprofile')):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('/')
    
    attendance = get_object_or_404(Attendance, id=attendance_id)
    if not attendance.check_out:
        attendance.checkout()
        messages.success(request, f'{attendance.member.user.full_name} checked out successfully!')
    else:
        messages.info(request, 'Member already checked out.')
    
    return redirect('gym_management:attendance_list')


# ==================== MEMBER DASHBOARD ====================

class MemberDashboardView(MemberRequiredMixin, TemplateView):
    """Member dashboard showing subscription and attendance."""
    template_name = 'gym_management/member_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        # Current subscription
        context['current_subscription'] = member.subscriptions.filter(status='active').first()
        
        # Recent attendance
        context['recent_attendance'] = member.attendance_records.order_by('-check_in')[:10]
        
        # Attendance this month
        today = date.today()
        first_day = today.replace(day=1)
        context['attendance_this_month'] = member.attendance_records.filter(
            date__gte=first_day
        ).count()
        
        # Last check-in
        context['last_checkin'] = member.attendance_records.order_by('-check_in').first()
        
        return context


class MySubscriptionView(MemberRequiredMixin, TemplateView):
    """Member's subscription details."""
    template_name = 'gym_management/my_subscription.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        context['current_subscription'] = member.subscriptions.filter(status='active').first()
        context['subscription_history'] = member.subscriptions.order_by('-created_at')[:5]
        context['available_plans'] = MembershipPlan.objects.filter(is_active=True)
        
        return context


class MyAttendanceView(MemberRequiredMixin, TemplateView):
    """Member's attendance history."""
    template_name = 'gym_management/my_attendance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        context['attendance_records'] = member.attendance_records.order_by('-check_in')[:30]
        
        # Stats
        today = date.today()
        first_day = today.replace(day=1)
        context['attendance_this_month'] = member.attendance_records.filter(
            date__gte=first_day
        ).count()
        
        # Last 7 days
        week_ago = today - timedelta(days=7)
        context['attendance_this_week'] = member.attendance_records.filter(
            date__gte=week_ago
        ).count()
        
        return context


# ==================== TRAINER DASHBOARD ====================

class TrainerDashboardView(TrainerRequiredMixin, TemplateView):
    """Trainer dashboard."""
    template_name = 'gym_management/trainer_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trainer = self.request.user.trainer
        
        # Total active members
        context['total_members'] = Member.objects.filter(is_active=True).count()
        
        # Today's attendance
        context['attendance_today'] = Attendance.objects.filter(date=date.today()).count()
        
        # Recent attendance
        context['recent_attendance'] = Attendance.objects.select_related(
            'member__user'
        ).order_by('-check_in')[:15]
        
        return context


# ==================== STAFF DASHBOARD ====================

class StaffDashboardView(StaffRequiredMixin, TemplateView):
    """Staff dashboard for check-in/check-out."""
    template_name = 'gym_management/staff_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Today's attendance
        today = date.today()
        context['attendance_today'] = Attendance.objects.filter(date=today).select_related(
            'member__user'
        ).order_by('-check_in')
        
        # Active members (currently checked in, not checked out)
        context['currently_present'] = Attendance.objects.filter(
            date=today,
            check_out__isnull=True
        ).select_related('member__user').order_by('-check_in')
        
        # All active members for quick check-in
        context['active_members'] = Member.objects.filter(is_active=True).select_related('user').order_by('user__full_name')
        
        return context

