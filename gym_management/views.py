import io
import json
import logging

import qrcode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy
from django.db import transaction, IntegrityError
from django.db.models import Count, Sum, Q, Avg, Prefetch, F
from django.http import HttpResponseNotAllowed, Http404, HttpResponse, HttpResponseForbidden
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from datetime import date, timedelta
from django_ratelimit.decorators import ratelimit
from accounts.mixins import AdminRequiredMixin, TrainerRequiredMixin, StaffRequiredMixin, MemberRequiredMixin, StaffOrAdminRequiredMixin
from accounts.models import Member, Trainer, Staff, User
from accounts.utils import get_user_role, can_manage_users, can_manage_payments, can_view_reports
from .models import MembershipPlan, Subscription, Payment, Attendance, Notification
from .mixins import ObjectOwnershipMixin, get_client_ip
from .forms import (
    MemberCreateForm, MemberUpdateForm, MembershipPlanForm,
    SubscriptionForm, PaymentCreateForm
)
from .services import SubscriptionService, AttendanceService, PaymentService


audit_logger = logging.getLogger('security.audit')


class AdminCapabilityMixin(LoginRequiredMixin):
    permission_checker = None
    permission_denied_message = 'You do not have permission to access this page.'

    def dispatch(self, request, *args, **kwargs):
        checker = getattr(type(self), 'permission_checker', None)
        if checker and not (request.user.is_superuser or checker(request.user)):
            messages.error(request, self.permission_denied_message)
            raise PermissionDenied(self.permission_denied_message)
        return super().dispatch(request, *args, **kwargs)


def has_staff_or_admin_attendance_access(user):
    role = get_user_role(user)
    return user.is_authenticated and (user.is_superuser or role in {'admin', 'staff'})


# ==================== ADMIN DASHBOARD ====================

class AdminDashboardView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Admin dashboard with overview statistics (optimized queries)."""
    template_name = 'gym_management/admin_dashboard.html'
    permission_checker = can_view_reports
    permission_denied_message = 'You do not have permission to view reports.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Efficient aggregate queries (total registered members for dashboard metrics)
        context['total_members'] = Member.all_objects.count()
        context['total_trainers'] = Trainer.objects.filter(is_active=True).count()
        context['total_staff'] = Staff.objects.filter(is_active=True).count()
        context['active_subscriptions'] = Subscription.objects.filter(status='active').count()
        
        # Revenue this month (single query)
        today = timezone.localdate()
        first_day = today.replace(day=1)
        revenue_data = Payment.objects.filter(
            status='completed',
            completed_at__gte=first_day
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        context['revenue_this_month'] = revenue_data['total'] or 0
        context['payments_this_month'] = revenue_data['count']
        
        # Today's attendance
        context['attendance_today'] = Attendance.objects.filter(date=today).count()
        
        # Recent activities with optimized select_related
        context['recent_subscriptions'] = Subscription.objects.select_related(
            'member__user', 'plan'
        ).order_by('-created_at')[:5]
        
        context['recent_payments'] = Payment.objects.select_related(
            'subscription__member__user', 'subscription__plan'
        ).order_by('-initiated_at')[:5]
        
        context['recent_attendance'] = Attendance.objects.select_related(
            'member__user'
        ).order_by('-check_in')[:10]
        
        # Expiring subscriptions (next 7 days) - optimized
        next_week = today + timedelta(days=7)
        context['expiring_soon'] = Subscription.objects.filter(
            status='active',
            end_date__gte=today,
            end_date__lte=next_week
        ).select_related('member__user', 'plan').order_by('end_date')
        
        return context


# ==================== MEMBER MANAGEMENT ====================

class MemberListView(AdminRequiredMixin, AdminCapabilityMixin, ListView):
    """List all members with search and filter."""
    model = Member
    template_name = 'gym_management/member_list.html'
    context_object_name = 'members'
    paginate_by = 20
    permission_checker = can_manage_users
    permission_denied_message = 'You do not have permission to manage users.'
    
    def get_queryset(self):
        queryset = Member.objects.select_related('user')
        
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


class MemberDetailView(AdminRequiredMixin, AdminCapabilityMixin, ObjectOwnershipMixin, DetailView):
    """Detailed view of a member with subscriptions, payments, and attendance."""
    model = Member
    template_name = 'gym_management/member_detail.html'
    context_object_name = 'member'
    required_admin_permission = 'can_manage_users'
    audit_object_name = 'member'
    permission_checker = can_manage_users
    permission_denied_message = 'You do not have permission to manage users.'

    def get_queryset(self):
        return Member.objects.select_related('user')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = context['member']
        
        # Optimized queries with select_related
        context['subscriptions'] = member.subscriptions.select_related('plan').order_by('-created_at')
        context['payments'] = Payment.objects.filter(
            subscription__member=member
        ).select_related('subscription__plan').order_by('-initiated_at')[:10]
        context['attendance_records'] = member.attendance_records.order_by('-check_in')[:20]
        
        # Current subscription
        context['current_subscription'] = member.subscriptions.filter(status='active').first()
        
        # Available plans for quick assignment
        context['available_plans'] = MembershipPlan.objects.filter(is_active=True).order_by('price')
        
        # Attendance stats this month
        today = timezone.localdate()
        first_day = today.replace(day=1)
        context['attendance_this_month'] = member.attendance_records.filter(
            date__gte=first_day
        ).count()
        
        return context


class MemberCreateView(AdminRequiredMixin, AdminCapabilityMixin, CreateView):
    """Create a new member with user account."""
    model = Member
    form_class = MemberCreateForm
    template_name = 'gym_management/member_form.html'
    success_url = reverse_lazy('gym_management:member_list')
    permission_checker = can_manage_users
    permission_denied_message = 'You do not have permission to manage users.'
    
    def form_valid(self, form):
        # Create user account first
        user = User.objects.create_user(
            email=form.cleaned_data['email'],
            username=form.cleaned_data.get('username') or None,
            password=form.cleaned_data['password'],
            full_name=form.cleaned_data['full_name'],
            phone=form.cleaned_data.get('phone', ''),
            is_verified=True  # Admin-created accounts are pre-verified
        )
        
        # Create member profile
        member = form.save(commit=False)
        member.user = user
        member.save()
        
        messages.success(self.request, f'Member {user.full_name} created successfully!')
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add New Member'
        context['submit_text'] = 'Create Member'
        return context


class MemberUpdateView(AdminRequiredMixin, AdminCapabilityMixin, UpdateView):
    """Update member information."""
    model = Member
    form_class = MemberUpdateForm
    template_name = 'gym_management/member_form.html'
    permission_checker = can_manage_users
    permission_denied_message = 'You do not have permission to manage users.'
    
    def get_success_url(self):
        return reverse_lazy('gym_management:member_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        # Update user fields
        member = form.save(commit=False)
        member.user.full_name = form.cleaned_data['full_name']
        member.user.phone = form.cleaned_data.get('phone', '')
        member.user.save()
        member.save()
        
        messages.success(self.request, f'Member {member.user.full_name} updated successfully!')
        return redirect(self.get_success_url())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Member'
        context['submit_text'] = 'Update Member'
        return context


class MemberDeleteView(AdminRequiredMixin, AdminCapabilityMixin, DeleteView):
    """Soft delete (deactivate) a member."""
    model = Member
    template_name = 'gym_management/member_confirm_delete.html'
    success_url = reverse_lazy('gym_management:member_list')
    permission_checker = can_manage_users
    permission_denied_message = 'You do not have permission to manage users.'
    
    def delete(self, request, *args, **kwargs):
        member = self.get_object()
        member.is_active = False
        member.user.is_active = False
        member.save()
        member.user.save()
        
        messages.success(request, f'Member {member.user.full_name} has been deactivated.')
        return redirect(self.success_url)


# ==================== MEMBERSHIP PLANS ====================

class MembershipPlanListView(AdminRequiredMixin, AdminCapabilityMixin, ListView):
    """List all membership plans."""
    model = MembershipPlan
    template_name = 'gym_management/plan_list.html'
    context_object_name = 'plans'
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage membership plans.'
    
    def get_queryset(self):
        return MembershipPlan.objects.all().order_by('price')


class MembershipPlanCreateView(AdminRequiredMixin, AdminCapabilityMixin, CreateView):
    """Create a new membership plan."""
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'gym_management/plan_form.html'
    success_url = reverse_lazy('gym_management:plan_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage membership plans.'
    
    def form_valid(self, form):
        messages.success(self.request, f'Membership plan "{form.instance.name}" created successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Membership Plan'
        context['submit_text'] = 'Create Plan'
        return context


class MembershipPlanUpdateView(AdminRequiredMixin, AdminCapabilityMixin, UpdateView):
    """Update a membership plan."""
    model = MembershipPlan
    form_class = MembershipPlanForm
    template_name = 'gym_management/plan_form.html'
    success_url = reverse_lazy('gym_management:plan_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage membership plans.'
    
    def form_valid(self, form):
        messages.success(self.request, f'Membership plan "{form.instance.name}" updated successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Membership Plan'
        context['submit_text'] = 'Update Plan'
        return context


class MembershipPlanDeleteView(AdminRequiredMixin, AdminCapabilityMixin, DeleteView):
    """Soft delete (deactivate) a membership plan."""
    model = MembershipPlan
    template_name = 'gym_management/plan_confirm_delete.html'
    success_url = reverse_lazy('gym_management:plan_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage membership plans.'
    
    def delete(self, request, *args, **kwargs):
        plan = self.get_object()
        plan.is_active = False
        plan.save()
        
        messages.success(request, f'Membership plan "{plan.name}" has been deactivated.')
        return redirect(self.success_url)


# ==================== SUBSCRIPTIONS ====================

class SubscriptionListView(AdminRequiredMixin, AdminCapabilityMixin, ListView):
    """List all subscriptions with filters."""
    model = Subscription
    template_name = 'gym_management/subscription_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 20
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage subscriptions.'
    
    def get_queryset(self):
        queryset = Subscription.objects.select_related('member__user', 'plan').all()
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.order_by('-created_at')


class SubscriptionCreateView(AdminRequiredMixin, AdminCapabilityMixin, CreateView):
    """Create a new subscription for a member."""
    model = Subscription
    form_class = SubscriptionForm
    template_name = 'gym_management/subscription_form.html'
    success_url = reverse_lazy('gym_management:subscription_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage subscriptions.'
    
    def form_valid(self, form):
        if not can_manage_payments(self.request.user):
            raise PermissionDenied('You do not have permission to manage subscriptions.')

        try:
            subscription = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        audit_logger.info(
            'SUBSCRIPTION_CREATE | user=%s | role=%s | subscription_id=%s | member_id=%s | plan_id=%s | status=%s | ip=%s',
            self.request.user.email,
            get_user_role(self.request.user),
            subscription.id,
            subscription.member.id,
            subscription.plan.id,
            subscription.status,
            get_client_ip(self.request),
        )
        messages.success(
            self.request,
            f'Subscription created for {subscription.member.user.full_name}. '
            f'Please create a payment to activate it.'
        )
        return redirect(f"{reverse('gym_management:payment_create')}?subscription={subscription.pk}")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Subscription'
        context['submit_text'] = 'Create & Add Payment'
        context['is_update'] = False
        # Inject plan durations/prices for real-time end date preview
        plans = MembershipPlan.objects.filter(is_active=True).values('id', 'duration_days', 'price', 'name')
        context['plan_data_json'] = json.dumps({str(p['id']): {'duration_days': p['duration_days'], 'price': str(p['price']), 'name': p['name']} for p in plans})
        return context


class SubscriptionUpdateView(AdminRequiredMixin, AdminCapabilityMixin, UpdateView):
    """Update subscription details without mutating payment records."""
    model = Subscription
    form_class = SubscriptionForm
    template_name = 'gym_management/subscription_form.html'
    success_url = reverse_lazy('gym_management:subscription_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage subscriptions.'
    
    def form_valid(self, form):
        if not can_manage_payments(self.request.user):
            raise PermissionDenied('You do not have permission to manage subscriptions.')

        original_subscription = Subscription.objects.select_related('plan').get(pk=self.object.pk)
        original_status = original_subscription.status
        original_plan_name = original_subscription.plan.name

        try:
            subscription, plan_changed = SubscriptionService.update_subscription(
                subscription=self.object,
                plan=form.cleaned_data['plan'],
                start_date=form.cleaned_data['start_date'],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        audit_logger.info(
            'SUBSCRIPTION_UPDATE | user=%s | role=%s | source_subscription_id=%s | result_subscription_id=%s | old_status=%s | new_status=%s | old_plan=%s | new_plan=%s | plan_changed=%s | ip=%s',
            self.request.user.email,
            get_user_role(self.request.user),
            self.object.id,
            subscription.id,
            original_status,
            subscription.status,
            original_plan_name,
            subscription.plan.name,
            plan_changed,
            get_client_ip(self.request),
        )

        if plan_changed:
            messages.success(self.request, 'New subscription created. Please record payment.')
            return redirect(f"{reverse('gym_management:payment_create')}?subscription={subscription.pk}")

        messages.success(self.request, 'Subscription updated successfully.')
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subscription = self.object
        context['title'] = 'Edit Subscription'
        context['submit_text'] = 'Update Subscription'
        context['is_update'] = True
        context['subscription'] = subscription
        context['member_name'] = subscription.member.user.full_name
        context['member_email'] = subscription.member.user.email
        context['current_plan'] = subscription.plan
        plans = MembershipPlan.objects.filter(is_active=True).values('id', 'duration_days', 'price', 'name')
        context['plan_data_json'] = json.dumps({str(p['id']): {'duration_days': p['duration_days'], 'price': str(p['price']), 'name': p['name']} for p in plans})
        return context


class SubscriptionCancelView(AdminRequiredMixin, AdminCapabilityMixin, UpdateView):
    """Cancel a subscription."""
    model = Subscription
    fields = []
    template_name = 'gym_management/subscription_confirm_cancel.html'
    success_url = reverse_lazy('gym_management:subscription_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to cancel subscriptions.'
    
    def form_valid(self, form):
        if not can_manage_payments(self.request.user):
            raise PermissionDenied('You do not have permission to cancel subscriptions.')

        subscription = self.get_object()
        subscription.status = 'cancelled'
        subscription.save()

        audit_logger.warning(
            'SUBSCRIPTION_CANCEL | user=%s | role=%s | subscription_id=%s | member_id=%s | ip=%s',
            self.request.user.email,
            get_user_role(self.request.user),
            subscription.id,
            subscription.member.id,
            get_client_ip(self.request),
        )
        
        messages.success(
            self.request,
            f'Subscription for {subscription.member.user.full_name} has been cancelled.'
        )
        return redirect(self.success_url)


@login_required
@require_POST
def assign_subscription_to_member(request, member_id):
    """
    Quick subscription assignment workflow for a specific member.
    Creates subscription and payment in one transaction.
    """
    if not can_manage_payments(request.user):
        raise PermissionDenied('You do not have permission to assign subscriptions.')
    
    member = get_object_or_404(Member.objects.select_related('user'), id=member_id)
    
    plan_id = request.POST.get('plan_id')
    payment_method = request.POST.get('payment_method', 'cash')
    
    try:
        plan = MembershipPlan.objects.get(id=plan_id, is_active=True)
        
        subscription, payment = SubscriptionService.create_subscription_with_payment(
            member=member,
            plan=plan,
            payment_method=payment_method
        )

        audit_logger.warning(
            'SUBSCRIPTION_ASSIGN | user=%s | role=%s | member_id=%s | subscription_id=%s | payment_id=%s | payment_method=%s | ip=%s',
            request.user.email,
            get_user_role(request.user),
            member.id,
            subscription.id,
            payment.id,
            payment_method,
            get_client_ip(request),
        )
        
        messages.success(
            request,
            f'Subscription assigned to {member.user.full_name}! '
            f'Payment of NPR {payment.amount} recorded.'
        )
        return redirect('gym_management:member_detail', pk=member.id)
    
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    except ValueError:
        messages.error(request, 'Unable to assign subscription due to validation rules.')
    except MembershipPlan.DoesNotExist:
        messages.error(request, 'Selected plan not found.')
    except IntegrityError:
        messages.error(request, 'A conflicting subscription was detected. Please retry.')
    
    return redirect('gym_management:member_detail', pk=member.id)


# ==================== PAYMENTS ====================

class PaymentListView(AdminRequiredMixin, AdminCapabilityMixin, ListView):
    """List all payments with filters."""
    model = Payment
    template_name = 'gym_management/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage payments.'
    
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


@method_decorator(ratelimit(key='user', rate='20/m', method='POST', block=False), name='dispatch')
class PaymentCreateView(AdminRequiredMixin, AdminCapabilityMixin, CreateView):
    """Create a payment for a subscription."""
    model = Payment
    form_class = PaymentCreateForm
    template_name = 'gym_management/payment_form.html'
    success_url = reverse_lazy('gym_management:payment_list')
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage payments.'
    
    def get_initial(self):
        initial = super().get_initial()
        
        # Pre-fill subscription if provided in URL
        subscription_id = self.request.GET.get('subscription')
        if subscription_id:
            try:
                subscription = Subscription.objects.get(pk=subscription_id)
                initial['subscription'] = subscription
                # SECURITY NOTE: Amount is now calculated server-side in form.save()
            except Subscription.DoesNotExist:
                pass
        
        return initial
    
    def form_valid(self, form):
        if not can_manage_payments(self.request.user):
            raise PermissionDenied('You do not have permission to manage payments.')

        if getattr(self.request, 'limited', False):
            audit_logger.warning(
                'RATE_LIMIT_BLOCK | user=%s | role=%s | endpoint=payment_create | method=%s | path=%s | ip=%s',
                self.request.user.email,
                get_user_role(self.request.user),
                self.request.method,
                self.request.path,
                get_client_ip(self.request),
            )
            messages.error(self.request, 'Too many payment attempts. Please wait a minute and try again.')
            return redirect(self.success_url)

        # Save with default pending status.
        # All financial transition logic (completion, subscription activation,
        # old-subscription expiry) is centralised in PaymentService.complete_payment().
        try:
            payment = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        if payment.payment_method in ['cash', 'card']:
            try:
                payment, expired_count = PaymentService.complete_payment(payment)
            except (ValidationError, ValueError) as exc:
                form.add_error(None, exc)
                return self.form_invalid(form)

            audit_logger.info(
                'PAYMENT_CREATE | user=%s | role=%s | payment_id=%s | transaction_id=%s | method=%s | status=%s | ip=%s',
                self.request.user.email,
                get_user_role(self.request.user),
                payment.pk,
                payment.transaction_id,
                payment.payment_method,
                payment.status,
                get_client_ip(self.request),
            )

            member_name = payment.subscription.member.user.full_name
            if payment.subscription.status == 'active':
                if expired_count:
                    messages.success(
                        self.request,
                        f'Payment completed! Previous subscription expired and new subscription activated for {member_name}.'
                    )
                else:
                    messages.success(
                        self.request,
                        f'Payment completed! Subscription activated for {member_name}.'
                    )
            else:
                messages.success(self.request, 'Payment recorded successfully!')
        else:
            # Online payments remain pending until gateway confirmation.
            audit_logger.info(
                'PAYMENT_CREATE | user=%s | role=%s | payment_id=%s | transaction_id=%s | method=%s | status=%s | ip=%s',
                self.request.user.email,
                get_user_role(self.request.user),
                payment.pk,
                payment.transaction_id,
                payment.payment_method,
                payment.status,
                get_client_ip(self.request),
            )
            messages.info(
                self.request,
                'Payment initiated. Waiting for payment gateway confirmation.'
            )

        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Record Payment'
        context['submit_text'] = 'Record Payment'
        return context


class PaymentDetailView(AdminRequiredMixin, AdminCapabilityMixin, ObjectOwnershipMixin, DetailView):
    """View payment details."""
    model = Payment
    template_name = 'gym_management/payment_detail.html'
    context_object_name = 'payment'
    required_admin_permission = 'can_manage_payments'
    audit_object_name = 'payment'
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to manage payments.'

    def get_queryset(self):
        return Payment.objects.select_related('subscription__member__user', 'subscription__plan')


# ==================== ATTENDANCE ====================

class AttendanceListView(StaffOrAdminRequiredMixin, ListView):
    """List attendance records with date filters."""
    model = Attendance
    template_name = 'gym_management/attendance_list.html'
    context_object_name = 'attendance_records'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = Attendance.objects.select_related('member__user').all()
        
        # Search by member name
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(member__user__full_name__icontains=search) |
                Q(member__user__email__icontains=search)
            )
        
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
            queryset = queryset.filter(date=timezone.localdate())
        
        return queryset.order_by('-check_in')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add active members for check-in dropdown
        context['active_members'] = Member.objects.select_related('user').order_by('user__full_name')
        # Currently present count
        today = timezone.localdate()
        context['currently_present_count'] = Attendance.objects.filter(
            date=today,
            check_out__isnull=True
        ).count()
        return context


class AttendanceQRView(StaffOrAdminRequiredMixin, View):
    """Serve a QR code PNG image encoding the self check-in URL."""

    def get(self, request):
        url = request.build_absolute_uri(reverse('gym_management:self_checkin'))
        qr = qrcode.make(url)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        buf.seek(0)
        return HttpResponse(buf.read(), content_type='image/png')


@login_required
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def attendance_checkin(request):
    """Check in a member with subscription validation."""
    if not has_staff_or_admin_attendance_access(request.user):
        raise PermissionDenied('You do not have permission to access this page.')
    
    if getattr(request, 'limited', False):
        audit_logger.warning(
            'RATE_LIMIT_BLOCK | user=%s | role=%s | endpoint=attendance_checkin | method=%s | path=%s | ip=%s',
            request.user.email,
            get_user_role(request.user),
            request.method,
            request.path,
            get_client_ip(request),
        )
        messages.error(request, 'Too many check-in attempts. Please wait and try again.')
        return redirect('gym_management:staff_dashboard')

    if request.method == 'POST':
        member_id = request.POST.get('member_id')
        
        try:
            member = Member.objects.select_related('user').get(id=member_id)

            attendance_record = AttendanceService.check_in_member(member)
            active_sub = member.subscriptions.filter(status='active').first()
            audit_logger.info(
                'ATTENDANCE_CHECKIN | user=%s | role=%s | member_id=%s | attendance_id=%s | ip=%s',
                request.user.email,
                get_user_role(request.user),
                member.id,
                attendance_record.id,
                get_client_ip(request),
            )
            success_message = f'{member.user.full_name} checked in successfully!'
            if active_sub:
                success_message = f'{success_message} Subscription expires on {active_sub.end_date}.'
            messages.success(request, success_message)
        
        except Member.DoesNotExist:
            messages.error(request, 'Member not found or inactive.')
        except ValueError as exc:
            messages.warning(request, str(exc))
        except IntegrityError:
            messages.error(request, 'Check-in could not be completed due to a concurrent request. Please try again.')
    
    # Redirect based on safe next parameter
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    if 'staff-dashboard' in str(next_url):
        return redirect('gym_management:staff_dashboard')
    return redirect('gym_management:attendance_list')


@login_required
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def attendance_checkout(request, attendance_id):
    """Check out a member with validation."""
    if not has_staff_or_admin_attendance_access(request.user):
        raise PermissionDenied('You do not have permission to access this page.')
    
    if getattr(request, 'limited', False):
        audit_logger.warning(
            'RATE_LIMIT_BLOCK | user=%s | role=%s | endpoint=attendance_checkout | method=%s | path=%s | ip=%s',
            request.user.email,
            get_user_role(request.user),
            request.method,
            request.path,
            get_client_ip(request),
        )
        messages.error(request, 'Too many checkout attempts. Please wait and try again.')
        return redirect('gym_management:staff_dashboard')

    try:
        attendance = get_object_or_404(
            Attendance.objects.select_related('member__user'),
            id=attendance_id
        )

        is_admin = request.user.is_superuser or get_user_role(request.user) == 'admin'
        if not is_admin:
            # SECURITY: Staff can only modify today's attendance records
            if attendance.date != timezone.localdate():
                audit_logger.warning(
                    'ATTENDANCE_CHECKOUT_DENIED | user=%s | role=%s | attendance_id=%s | reason=non_today_record | ip=%s',
                    request.user.email,
                    get_user_role(request.user),
                    attendance_id,
                    get_client_ip(request),
                )
                raise PermissionDenied('Staff can only modify today attendance records.')
            
            # SECURITY: Additional constraint - staff should only checkout attendance they managed
            # This prevents cross-shift manipulation
            if get_user_role(request.user) == 'staff' and not is_admin:
                # Allow checkout if:
                # 1. It's today's record AND
                # 2. It's within the same work shift (last 8 hours) OR staff explicitly assigned
                eight_hours_ago = timezone.now() - timedelta(hours=8)
                if attendance.check_in < eight_hours_ago:
                    audit_logger.warning(
                        'ATTENDANCE_CHECKOUT_DENIED | user=%s | role=%s | attendance_id=%s | reason=outside_shift_scope | check_in_time=%s | ip=%s',
                        request.user.email,
                        get_user_role(request.user),
                        attendance_id,
                        attendance.check_in.isoformat(),
                        get_client_ip(request),
                    )
                    raise PermissionDenied('Staff can only checkout attendance from current shift (last 8 hours).')
        
        if attendance.check_out:
            messages.info(
                request,
                f'{attendance.member.user.full_name} was already checked out at '
                f'{attendance.check_out.strftime("%I:%M %p")}.'
            )
        else:
            attendance = AttendanceService.check_out_member(attendance)
            duration = attendance.duration()

            audit_logger.info(
                'ATTENDANCE_CHECKOUT | user=%s | role=%s | member_id=%s | attendance_id=%s | duration_hours=%s | ip=%s',
                request.user.email,
                get_user_role(request.user),
                attendance.member.id,
                attendance.id,
                duration,
                get_client_ip(request),
            )
            
            messages.success(
                request,
                f'{attendance.member.user.full_name} checked out successfully! '
                f'Duration: {duration:.1f} hours.' if duration else 
                f'{attendance.member.user.full_name} checked out successfully!'
            )
    
    except PermissionDenied:
        raise
    except Http404:
        messages.error(request, 'Attendance record was not found.')
    except ValueError as exc:
        messages.warning(request, str(exc))
    
    # Redirect back using safe internal URL only
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    if 'staff-dashboard' in str(next_url):
        return redirect('gym_management:staff_dashboard')
    return redirect('gym_management:attendance_list')


# ==================== MEMBER DASHBOARD ====================

class MemberDashboardView(MemberRequiredMixin, TemplateView):
    """Member dashboard showing subscription and attendance (optimized)."""
    template_name = 'gym_management/member_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        # Current subscription with plan details
        context['current_subscription'] = member.subscriptions.select_related(
            'plan'
        ).filter(status='active').first()
        
        # Recent attendance (optimized - no N+1)
        context['recent_attendance'] = member.attendance_records.order_by('-check_in')[:10]
        
        # Attendance stats this month
        today = timezone.localdate()
        first_day = today.replace(day=1)
        attendance_this_month = member.attendance_records.filter(date__gte=first_day)
        
        context['attendance_this_month'] = attendance_this_month.count()
        
        # Calculate average workout duration this month (DB aggregation)
        completed_this_month = attendance_this_month.filter(check_out__isnull=False)
        avg_duration = completed_this_month.annotate(
            duration_delta=F('check_out') - F('check_in')
        ).aggregate(avg_duration=Avg('duration_delta'))['avg_duration']
        context['avg_workout_duration'] = round(avg_duration.total_seconds() / 3600, 1) if avg_duration else 0
        
        # Last check-in
        context['last_checkin'] = member.attendance_records.order_by('-check_in').first()
        
        # Check if currently checked in
        context['is_checked_in'] = member.attendance_records.filter(
            date=today,
            check_out__isnull=True
        ).exists()
        
        # Payment history (last 5)
        context['recent_payments'] = Payment.objects.filter(
            subscription__member=member,
            status='completed'
        ).select_related('subscription__plan').order_by('-completed_at')[:5]
        
        return context


class MySubscriptionView(MemberRequiredMixin, TemplateView):
    """Member's subscription details (optimized)."""
    template_name = 'gym_management/my_subscription.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        # Current subscription with plan
        context['current_subscription'] = member.subscriptions.select_related(
            'plan'
        ).filter(status='active').first()
        
        # Subscription history (optimized)
        context['subscription_history'] = member.subscriptions.select_related(
            'plan'
        ).order_by('-created_at')[:5]
        
        # Available plans
        context['available_plans'] = MembershipPlan.objects.filter(is_active=True).order_by('price')
        
        # Total payments for current subscription
        if context['current_subscription']:
            context['total_paid'] = Payment.objects.filter(
                subscription=context['current_subscription'],
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
        
        return context


class MyAttendanceView(MemberRequiredMixin, TemplateView):
    """Member's attendance history (optimized)."""
    template_name = 'gym_management/my_attendance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        # Recent attendance
        context['attendance_records'] = member.attendance_records.order_by('-check_in')[:30]
        
        # Stats
        today = timezone.localdate()
        first_day = today.replace(day=1)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Use aggregate for counts
        attendance_counts = member.attendance_records.filter(
            date__gte=first_day
        ).aggregate(
            this_month=Count('id', filter=Q(date__gte=first_day)),
            this_week=Count('id', filter=Q(date__gte=week_ago)),
            last_30_days=Count('id', filter=Q(date__gte=month_ago))
        )
        
        context['attendance_this_month'] = attendance_counts['this_month']
        context['attendance_this_week'] = attendance_counts['this_week']
        context['attendance_last_30_days'] = attendance_counts['last_30_days']
        
        # Average attendance per week (last 4 weeks)
        context['avg_per_week'] = round(attendance_counts['last_30_days'] / 4.0, 1)
        
        return context


# ==================== TRAINER DASHBOARD ====================

class TrainerDashboardView(TrainerRequiredMixin, TemplateView):
    """Trainer dashboard (optimized)."""
    template_name = 'gym_management/trainer_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trainer = self.request.user.trainer
        
        # Statistics (optimized)
        today = timezone.localdate()
        
        stats = {
            'total_members': Member.all_objects.count(),  # Total registered members
            'active_subscriptions': Subscription.objects.filter(status='active').count(),
            'attendance_today': Attendance.objects.filter(date=today).count(),
        }
        
        context.update(stats)
        
        # Recent attendance with member details (optimized)
        context['recent_attendance'] = Attendance.objects.select_related(
            'member__user'
        ).order_by('-check_in')[:15]
        
        # Today's checked-in members
        context['currently_present'] = Attendance.objects.filter(
            date=today,
            check_out__isnull=True
        ).select_related('member__user').count()
        
        # Weekly attendance trend
        week_ago = today - timedelta(days=7)
        context['attendance_this_week'] = Attendance.objects.filter(
            date__gte=week_ago
        ).count()
        
        return context


# ==================== STAFF DASHBOARD ====================

class StaffDashboardView(StaffRequiredMixin, TemplateView):
    """Staff dashboard for check-in/check-out (optimized)."""
    template_name = 'gym_management/staff_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.localdate()
        
        # Today's attendance with member details (single optimized query)
        context['attendance_today'] = Attendance.objects.filter(
            date=today
        ).select_related('member__user').order_by('-check_in')
        
        # Currently present (not checked out)
        currently_present_qs = Attendance.objects.filter(
            date=today,
            check_out__isnull=True
        ).select_related('member__user').order_by('-check_in')
        
        context['currently_present_list'] = currently_present_qs
        context['currently_present'] = currently_present_qs.count()
        
        # Today's stats
        context['today_checkins'] = Attendance.objects.filter(date=today).count()
        context['total_members'] = Member.all_objects.count()  # Total registered members
        
        # Active members for dropdown (optimized)
        context['active_members'] = Member.objects.select_related('user').order_by('user__full_name')
        
        # Active members with subscription status (for validation)
        # Prefetch active subscriptions to avoid N+1
        active_subscription_prefetch = Prefetch(
            'subscriptions',
            queryset=Subscription.objects.filter(status='active').select_related('plan'),
            to_attr='active_subs'
        )
        
        context['members_with_subscription'] = Member.objects.select_related('user').prefetch_related(
            active_subscription_prefetch
        ).order_by('user__full_name')
        
        return context


# ==================== ATTENDANCE REPORTS ====================

class AttendanceReportView(StaffOrAdminRequiredMixin, TemplateView):
    """Attendance reports and analytics."""
    template_name = 'gym_management/attendance_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.localdate()
        
        # Date range filters
        date_filter = self.request.GET.get('filter', 'today')
        
        if date_filter == 'today':
            start_date = today
            end_date = today
        elif date_filter == 'week':
            start_date = today - timedelta(days=7)
            end_date = today
        elif date_filter == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif date_filter == 'custom':
            start_str = self.request.GET.get('start_date')
            end_str = self.request.GET.get('end_date')
            try:
                start_date = date.fromisoformat(start_str) if start_str else today
                end_date = date.fromisoformat(end_str) if end_str else today
            except ValueError:
                start_date = today
                end_date = today
        else:
            start_date = today
            end_date = today
        
        context['date_filter'] = date_filter
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Stats
        attendance_records = Attendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        )
        
        context['total_visits'] = attendance_records.count()
        context['unique_members'] = attendance_records.values('member').distinct().count()
        
        # Average visits per day
        days_diff = (end_date - start_date).days + 1
        context['avg_visits_per_day'] = round(context['total_visits'] / days_diff, 1) if days_diff > 0 else 0
        
        # Peak hours analysis (group by hour)
        from django.db.models.functions import ExtractHour
        peak_hours = attendance_records.annotate(
            hour=ExtractHour('check_in')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('-count')[:3]
        
        context['peak_hours'] = [
            {'hour': f"{ph['hour']}:00", 'count': ph['count']}
            for ph in peak_hours
        ]
        
        # Top members by visits
        top_members = attendance_records.values(
            'member__user__full_name', 'member__id'
        ).annotate(
            visit_count=Count('id')
        ).order_by('-visit_count')[:10]
        
        context['top_members'] = top_members
        
        # Daily breakdown
        daily_stats = attendance_records.values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        context['daily_stats'] = daily_stats
        
        return context


# ==================== PHASE 2: ESEWA PAYMENT INTEGRATION ====================

class EsewaPaymentInitiateView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Initiate eSewa payment for a pending payment."""
    template_name = 'gym_management/esewa_payment.html'
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to process payments.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment_id = self.kwargs.get('payment_id')
        
        payment = get_object_or_404(
            Payment.objects.select_related('subscription__member__user', 'subscription__plan'),
            pk=payment_id,
            payment_method='esewa',
            status='pending'
        )
        
        from .services import EsewaPaymentService
        
        # Build callback URLs
        success_url = self.request.build_absolute_uri(
            reverse_lazy('gym_management:esewa_success')
        )
        failure_url = self.request.build_absolute_uri(
            reverse_lazy('gym_management:esewa_failure')
        )
        
        try:
            payment_data = EsewaPaymentService.initiate_payment(payment, success_url, failure_url)
            context['payment'] = payment
            context['payment_url'] = payment_data['payment_url']
            context['form_data'] = payment_data['form_data']
        except ValueError as e:
            messages.error(self.request, str(e))
            context['error'] = str(e)
        
        return context


@login_required
def esewa_success_callback(request):
    """Handle eSewa payment success callback."""
    from .services import EsewaPaymentService
    
    # eSewa sends data via GET parameters
    data = request.GET.get('data', '')
    
    if not data:
        messages.error(request, 'Invalid payment callback data.')
        return redirect('gym_management:payment_list')
    
    # Decode base64 data
    import base64
    import json as json_lib
    
    try:
        decoded_data = json_lib.loads(base64.b64decode(data).decode())
        
        transaction_uuid = decoded_data.get('transaction_uuid')
        esewa_transaction_code = decoded_data.get('transaction_code')
        esewa_ref_id = decoded_data.get('ref_id', '')
        signature = decoded_data.get('signature', '')
        total_amount = decoded_data.get('total_amount')
        status = decoded_data.get('status')
        
        if status != 'COMPLETE':
            messages.warning(request, f'Payment status: {status}')
            return redirect('gym_management:payment_list')
        
        success, message, payment = EsewaPaymentService.process_success_callback(
            transaction_uuid=transaction_uuid,
            esewa_transaction_code=esewa_transaction_code,
            esewa_ref_id=esewa_ref_id,
            signature=signature,
            total_amount=total_amount
        )
        
        if success:
            messages.success(request, message)
            if payment and payment.subscription:
                return redirect('gym_management:member_detail', pk=payment.subscription.member.pk)
        else:
            messages.error(request, message)
        
    except Exception as e:
        audit_logger.error(f'ESEWA_CALLBACK_ERROR | error={str(e)}')
        messages.error(request, 'Error processing payment callback.')
    
    return redirect('gym_management:payment_list')


@login_required
def esewa_failure_callback(request):
    """Handle eSewa payment failure callback."""
    from .services import EsewaPaymentService
    
    # eSewa sends data via GET parameters
    data = request.GET.get('data', '')
    
    if not data:
        messages.error(request, 'Payment was not completed.')
        return redirect('gym_management:payment_list')
    
    import base64
    import json as json_lib
    
    try:
        decoded_data = json_lib.loads(base64.b64decode(data).decode())
        transaction_uuid = decoded_data.get('transaction_uuid', '')
        
        if transaction_uuid:
            EsewaPaymentService.process_failure_callback(
                transaction_uuid=transaction_uuid,
                reason='User cancelled or payment failed.'
            )
        
        messages.warning(request, 'eSewa payment was not completed.')
        
    except Exception as e:
        audit_logger.error(f'ESEWA_FAILURE_CALLBACK_ERROR | error={str(e)}')
        messages.error(request, 'Payment was cancelled or failed.')
    
    return redirect('gym_management:payment_list')


# ==================== PHASE 2: ANALYTICS & REPORTING ====================

class RevenueReportView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Revenue analytics and reporting."""
    template_name = 'gym_management/reports/revenue_report.html'
    permission_checker = can_view_reports
    permission_denied_message = 'You do not have permission to view reports.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .services import AnalyticsService
        
        # Get date range from request
        today = timezone.localdate()
        date_range = self.request.GET.get('range', '30')
        
        if date_range == '7':
            start_date = today - timedelta(days=7)
        elif date_range == '30':
            start_date = today - timedelta(days=30)
        elif date_range == '90':
            start_date = today - timedelta(days=90)
        elif date_range == '365':
            start_date = today - timedelta(days=365)
        elif date_range == 'custom':
            try:
                start_date = date.fromisoformat(self.request.GET.get('start', str(today - timedelta(days=30))))
                end_date = date.fromisoformat(self.request.GET.get('end', str(today)))
            except ValueError:
                start_date = today - timedelta(days=30)
                end_date = today
        else:
            start_date = today - timedelta(days=30)
        
        if date_range != 'custom':
            end_date = today
        
        report = AnalyticsService.get_revenue_report(start_date, end_date)
        context.update(report)
        context['date_range'] = date_range
        
        # Prepare chart data as JSON
        context['daily_revenue_json'] = json.dumps([
            {'date': str(d['date']), 'total': float(d['total'])}
            for d in report['daily_revenue']
        ])
        
        context['revenue_by_method_json'] = json.dumps([
            {'method': m['payment_method'], 'total': float(m['total'])}
            for m in report['revenue_by_method']
        ])
        
        return context


class MembershipAnalyticsView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Membership analytics and insights."""
    template_name = 'gym_management/reports/membership_analytics.html'
    permission_checker = can_view_reports
    permission_denied_message = 'You do not have permission to view reports.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .services import AnalyticsService
        
        analytics = AnalyticsService.get_membership_analytics()
        context.update(analytics)
        
        # Prepare chart data
        context['subscription_by_plan_json'] = json.dumps([
            {'plan': s['plan__name'], 'count': s['count']}
            for s in analytics['subscription_by_plan']
        ])
        
        context['subscription_by_status_json'] = json.dumps([
            {'status': s['status'], 'count': s['count']}
            for s in analytics['subscription_by_status']
        ])
        
        return context


class AttendanceAnalyticsView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Attendance analytics and insights."""
    template_name = 'gym_management/reports/attendance_analytics.html'
    permission_checker = can_view_reports
    permission_denied_message = 'You do not have permission to view reports.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .services import AnalyticsService
        
        # Get date range
        today = timezone.localdate()
        date_range = self.request.GET.get('range', '30')
        
        if date_range == '7':
            start_date = today - timedelta(days=7)
        elif date_range == '30':
            start_date = today - timedelta(days=30)
        elif date_range == '90':
            start_date = today - timedelta(days=90)
        else:
            start_date = today - timedelta(days=30)
        
        analytics = AnalyticsService.get_attendance_analytics(start_date, today)
        context.update(analytics)
        context['date_range'] = date_range
        
        # Prepare chart data
        context['daily_attendance_json'] = json.dumps([
            {'date': str(d['date']), 'count': d['count']}
            for d in analytics['daily_attendance']
        ])
        
        context['peak_hours_json'] = json.dumps([
            {'hour': f"{h['hour']}:00", 'count': h['count']}
            for h in analytics['peak_hours']
        ])
        
        return context


class InactiveMembersReportView(AdminRequiredMixin, AdminCapabilityMixin, ListView):
    """Report of members with active subscriptions but no recent attendance."""
    template_name = 'gym_management/reports/inactive_members.html'
    context_object_name = 'inactive_members'
    permission_checker = can_view_reports
    permission_denied_message = 'You do not have permission to view reports.'
    
    def get_queryset(self):
        from .services import AnalyticsService
        days = int(self.request.GET.get('days', 14))
        return AnalyticsService.get_inactive_members(days)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['days'] = int(self.request.GET.get('days', 14))
        return context


# ==================== PHASE 2: EXPORT SYSTEM ====================


@login_required
def export_payments_csv(request):
    """Export payments to CSV."""
    if not can_manage_payments(request.user):
        raise PermissionDenied('You do not have permission to export payment data.')
    
    from .services import ExportService
    
    # Get date range from request
    today = timezone.localdate()
    start_str = request.GET.get('start', str(today - timedelta(days=30)))
    end_str = request.GET.get('end', str(today))
    
    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today
    
    csv_content = ExportService.export_payments_csv(start_date, end_date)
    
    response = HttpResponse(csv_content.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payments_{start_date}_{end_date}.csv"'
    
    audit_logger.info(
        'EXPORT_PAYMENTS | user=%s | role=%s | start=%s | end=%s | ip=%s',
        request.user.email, get_user_role(request.user),
        start_date, end_date, get_client_ip(request)
    )
    
    return response


@login_required
def export_members_csv(request):
    """Export members to CSV."""
    if not can_manage_users(request.user):
        raise PermissionDenied('You do not have permission to export member data.')
    
    from .services import ExportService
    
    include_subscription = request.GET.get('include_subscription', 'true').lower() == 'true'
    
    csv_content = ExportService.export_members_csv(include_subscription)
    
    response = HttpResponse(csv_content.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="members.csv"'
    
    audit_logger.info(
        'EXPORT_MEMBERS | user=%s | role=%s | ip=%s',
        request.user.email, get_user_role(request.user), get_client_ip(request)
    )
    
    return response


@login_required
def export_attendance_csv(request):
    """Export attendance to CSV."""
    if not has_staff_or_admin_attendance_access(request.user):
        raise PermissionDenied('You do not have permission to export attendance data.')
    
    from .services import ExportService
    
    # Get date range from request
    today = timezone.localdate()
    start_str = request.GET.get('start', str(today - timedelta(days=30)))
    end_str = request.GET.get('end', str(today))
    
    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today
    
    csv_content = ExportService.export_attendance_csv(start_date, end_date)
    
    response = HttpResponse(csv_content.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_{start_date}_{end_date}.csv"'
    
    audit_logger.info(
        'EXPORT_ATTENDANCE | user=%s | role=%s | start=%s | end=%s | ip=%s',
        request.user.email, get_user_role(request.user),
        start_date, end_date, get_client_ip(request)
    )
    
    return response


@login_required
def export_revenue_csv(request):
    """Export revenue report to CSV."""
    if not can_view_reports(request.user):
        raise PermissionDenied('You do not have permission to export revenue data.')
    
    from .services import ExportService
    
    # Get date range from request
    today = timezone.localdate()
    start_str = request.GET.get('start', str(today - timedelta(days=30)))
    end_str = request.GET.get('end', str(today))
    
    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        start_date = today - timedelta(days=30)
        end_date = today
    
    csv_content = ExportService.export_revenue_report_csv(start_date, end_date)
    
    response = HttpResponse(csv_content.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="revenue_{start_date}_{end_date}.csv"'
    
    audit_logger.info(
        'EXPORT_REVENUE | user=%s | role=%s | start=%s | end=%s | ip=%s',
        request.user.email, get_user_role(request.user),
        start_date, end_date, get_client_ip(request)
    )
    
    return response


# ==================== PHASE 2: SUBSCRIPTION UPGRADE ====================

class SubscriptionUpgradeView(AdminRequiredMixin, AdminCapabilityMixin, TemplateView):
    """Upgrade a member's subscription to a higher plan."""
    template_name = 'gym_management/subscription_upgrade.html'
    permission_checker = can_manage_payments
    permission_denied_message = 'You do not have permission to upgrade subscriptions.'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subscription_id = self.kwargs.get('pk')
        
        subscription = get_object_or_404(
            Subscription.objects.select_related('member__user', 'plan'),
            pk=subscription_id,
            status='active'
        )
        
        context['subscription'] = subscription
        context['current_plan'] = subscription.plan
        context['member'] = subscription.member
        
        # Get available upgrade plans (higher priced)
        context['upgrade_plans'] = MembershipPlan.objects.filter(
            is_active=True,
            price__gt=subscription.plan.price
        ).order_by('price')
        
        # Calculate prorated credit
        today = timezone.localdate()
        if subscription.end_date > today:
            remaining_days = (subscription.end_date - today).days
            daily_rate = subscription.plan.price / subscription.plan.duration_days
            context['credit_available'] = round(daily_rate * remaining_days, 2)
        else:
            context['credit_available'] = 0
        
        return context


@login_required
@require_POST
def process_subscription_upgrade(request, pk):
    """Process subscription upgrade."""
    if not can_manage_payments(request.user):
        raise PermissionDenied('You do not have permission to upgrade subscriptions.')
    
    from .services import SubscriptionService
    
    subscription = get_object_or_404(
        Subscription.objects.select_related('member__user', 'plan'),
        pk=pk,
        status='active'
    )
    
    new_plan_id = request.POST.get('new_plan_id')
    payment_method = request.POST.get('payment_method', 'cash')
    prorate = request.POST.get('prorate', 'true').lower() == 'true'
    
    try:
        new_plan = MembershipPlan.objects.get(pk=new_plan_id, is_active=True)
        
        new_subscription, payment, credit_applied = SubscriptionService.upgrade_subscription(
            member=subscription.member,
            new_plan=new_plan,
            payment_method=payment_method,
            prorate=prorate
        )
        
        audit_logger.info(
            'SUBSCRIPTION_UPGRADE_COMPLETE | user=%s | role=%s | member_id=%s | old_plan=%s | new_plan=%s | credit=%s | ip=%s',
            request.user.email, get_user_role(request.user),
            subscription.member.id, subscription.plan.name, new_plan.name,
            credit_applied, get_client_ip(request)
        )
        
        messages.success(
            request,
            f'Subscription upgraded to {new_plan.name} for {subscription.member.user.full_name}! '
            f'Credit applied: NPR {credit_applied:.2f}'
        )
        
        if payment.payment_method == 'esewa' and payment.status == 'pending':
            return redirect('gym_management:esewa_initiate', payment_id=payment.pk)
        
        return redirect('gym_management:member_detail', pk=subscription.member.pk)
        
    except MembershipPlan.DoesNotExist:
        messages.error(request, 'Selected plan not found.')
    except ValueError as e:
        messages.error(request, str(e))
    
    return redirect('gym_management:subscription_upgrade', pk=pk)


# ==================== PHASE 2: NOTIFICATIONS ====================

class NotificationListView(MemberRequiredMixin, ListView):
    """List notifications for the current member."""
    template_name = 'gym_management/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        from .models import Notification
        member = self.request.user.member
        return Notification.objects.filter(
            member=member,
            channel__in=['dashboard', 'both']
        ).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import Notification
        member = self.request.user.member
        context['unread_count'] = Notification.objects.filter(
            member=member,
            is_read=False,
            channel__in=['dashboard', 'both']
        ).count()
        return context


@login_required
@require_POST
def mark_notification_read(request, pk):
    """Mark a notification as read."""
    from .models import Notification
    
    # Ensure user has member profile
    if not hasattr(request.user, 'member'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return HttpResponseForbidden('Only members can access notifications.')
        messages.error(request, 'Only members can access notifications.')
        return redirect('gym_management:dashboard')
    
    notification = get_object_or_404(
        Notification,
        pk=pk,
        member=request.user.member
    )
    
    notification.mark_as_read()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(status=204)
    
    return redirect('gym_management:notifications')


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all notifications as read."""
    from .services import NotificationService
    
    # Ensure user has member profile
    if not hasattr(request.user, 'member'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return HttpResponseForbidden('Only members can access notifications.')
        messages.error(request, 'Only members can access notifications.')
        return redirect('gym_management:dashboard')
    
    NotificationService.mark_notifications_read(request.user.member)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(status=204)
    
    messages.success(request, 'All notifications marked as read.')
    return redirect('gym_management:notifications')


# ==================== PHASE 2: PAYMENT RECEIPT ====================

class PaymentReceiptView(LoginRequiredMixin, DetailView):
    """Generate payment receipt for members or admin."""
    template_name = 'gym_management/payment_receipt.html'
    context_object_name = 'payment'
    
    def get_queryset(self):
        queryset = Payment.objects.select_related(
            'subscription__member__user', 'subscription__plan'
        )
        
        # Members can only view their own receipts
        user = self.request.user
        if hasattr(user, 'member'):
            queryset = queryset.filter(subscription__member=user.member)
        elif not (user.is_superuser or hasattr(user, 'adminprofile')):
            # Non-admin, non-member users cannot view receipts
            queryset = queryset.none()
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment = context['payment']
        
        # Format receipt data
        context['receipt_number'] = f"RCP-{payment.transaction_id}"
        context['issue_date'] = payment.completed_at or payment.initiated_at
        
        return context


# ==================== MANAGEMENT COMMAND VIEWS (Admin Only) ====================

@login_required
@require_POST
def run_expiry_notifications(request):
    """Manually trigger expiry notification processing (admin only)."""
    if not request.user.is_superuser:
        raise PermissionDenied('Only superusers can run this command.')
    
    from .services import NotificationService, SubscriptionService
    
    # First expire any past-due subscriptions
    expired_count = SubscriptionService.check_and_expire_subscriptions()
    
    # Then process notifications
    stats = NotificationService.process_expiry_notifications()
    
    audit_logger.info(
        'MANUAL_EXPIRY_NOTIFICATIONS | user=%s | expired=%s | notifications=%s | emails=%s | ip=%s',
        request.user.email, expired_count,
        stats['notifications_created'], stats['emails_sent'],
        get_client_ip(request)
    )
    
    messages.success(
        request,
        f'Processed expiry notifications: {expired_count} subscriptions expired, '
        f'{stats["notifications_created"]} notifications created, '
        f'{stats["emails_sent"]} emails sent.'
    )
    
    return redirect('gym_management:admin_dashboard')


# ==================== PHASE 3: QR SELF CHECK-IN/OUT ====================

class SelfCheckInView(MemberRequiredMixin, TemplateView):
    """Generate a short-lived check-in token and redirect to confirmation."""

    def get(self, request, *args, **kwargs):
        session = AttendanceService.create_qr_session(request.user.member, 'checkin')
        audit_logger.info(
            'SELF_CHECKIN_SESSION_CREATED | user=%s | member_id=%s | session_id=%s | expires_at=%s | ip=%s',
            request.user.email,
            request.user.member.id,
            session.pk,
            session.expires_at.isoformat(),
            get_client_ip(request),
        )
        return redirect(f'{reverse("gym_management:self_checkin_confirm")}?token={session.pk}')


class SelfCheckInConfirmView(MemberRequiredMixin, TemplateView):
    """Render and process the geofenced, tokenized check-in confirmation flow."""

    template_name = 'gym_management/self_checkin_confirm.html'

    def _build_context(self, token, **kwargs):
        context = self.get_context_data(**kwargs)
        context['session_token'] = token

        if not token:
            context['error_message'] = AttendanceService.INVALID_QR_MESSAGE
            return context

        try:
            session, member = AttendanceService.validate_qr_session(token, self.request.user, 'checkin')
        except ValueError as exc:
            context['error_message'] = str(exc)
            return context

        today = timezone.localdate()
        context['session_token'] = str(session.pk)
        context['session_expires_at'] = session.expires_at
        context['active_subscription'] = member.subscriptions.select_related('plan').filter(status='active').first()
        context['active_attendance'] = member.attendance_records.filter(
            date=today,
            check_out__isnull=True,
        ).first()
        return context

    def get(self, request, *args, **kwargs):
        context = self._build_context(request.GET.get('token'), **kwargs)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        token = request.POST.get('token')
        context = self._build_context(token, **kwargs)

        if context.get('error_message'):
            return self.render_to_response(context)

        try:
            attendance, active_sub, distance_meters = AttendanceService.process_self_check_in(
                request.user,
                token,
                request.POST.get('latitude'),
                request.POST.get('longitude'),
            )
            context['check_in_success'] = True
            context['attendance'] = attendance
            context['check_in_time'] = attendance.check_in
            context['active_subscription'] = active_sub
            context['distance_meters'] = round(distance_meters, 2)
            audit_logger.info(
                'SELF_CHECKIN_SUCCESS | user=%s | member_id=%s | attendance_id=%s | session_id=%s | distance_meters=%.2f | ip=%s',
                request.user.email,
                request.user.member.id,
                attendance.id,
                token,
                distance_meters,
                get_client_ip(request),
            )
        except ValueError as exc:
            context['error_message'] = str(exc)
            audit_logger.warning(
                'SELF_CHECKIN_FAILED | user=%s | member_id=%s | session_id=%s | reason=%s | ip=%s',
                request.user.email,
                request.user.member.id,
                token,
                str(exc),
                get_client_ip(request),
            )

        return self.render_to_response(context)


class SelfCheckOutView(MemberRequiredMixin, TemplateView):
    """Generate a short-lived check-out token and redirect to confirmation."""

    def get(self, request, *args, **kwargs):
        session = AttendanceService.create_qr_session(request.user.member, 'checkout')
        audit_logger.info(
            'SELF_CHECKOUT_SESSION_CREATED | user=%s | member_id=%s | session_id=%s | expires_at=%s | ip=%s',
            request.user.email,
            request.user.member.id,
            session.pk,
            session.expires_at.isoformat(),
            get_client_ip(request),
        )
        return redirect(f'{reverse("gym_management:self_checkout_confirm")}?token={session.pk}')


class SelfCheckOutConfirmView(MemberRequiredMixin, TemplateView):
    """Render and process the geofenced, tokenized check-out confirmation flow."""

    template_name = 'gym_management/self_checkout_confirm.html'

    def _build_context(self, token, **kwargs):
        context = self.get_context_data(**kwargs)
        context['session_token'] = token

        if not token:
            context['error_message'] = AttendanceService.INVALID_QR_MESSAGE
            return context

        try:
            session, member = AttendanceService.validate_qr_session(token, self.request.user, 'checkout')
        except ValueError as exc:
            context['error_message'] = str(exc)
            return context

        context['session_token'] = str(session.pk)
        context['session_expires_at'] = session.expires_at
        context['active_subscription'] = member.subscriptions.select_related('plan').filter(status='active').first()
        context['open_attendance'] = member.attendance_records.filter(check_out__isnull=True).first()
        return context

    def get(self, request, *args, **kwargs):
        context = self._build_context(request.GET.get('token'), **kwargs)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        token = request.POST.get('token')
        context = self._build_context(token, **kwargs)

        if context.get('error_message'):
            return self.render_to_response(context)

        try:
            attendance, distance_meters = AttendanceService.process_self_check_out(
                request.user,
                token,
                request.POST.get('latitude'),
                request.POST.get('longitude'),
            )
            duration = attendance.duration()
            context['checkout_success'] = True
            context['attendance'] = attendance
            context['duration'] = duration
            context['check_in_time'] = attendance.check_in
            context['check_out_time'] = attendance.check_out
            context['distance_meters'] = round(distance_meters, 2)
            audit_logger.info(
                'SELF_CHECKOUT_SUCCESS | user=%s | member_id=%s | attendance_id=%s | session_id=%s | duration_hours=%s | distance_meters=%.2f | ip=%s',
                request.user.email,
                request.user.member.id,
                attendance.id,
                token,
                duration,
                distance_meters,
                get_client_ip(request),
            )
        except ValueError as exc:
            context['error_message'] = str(exc)
            audit_logger.warning(
                'SELF_CHECKOUT_FAILED | user=%s | member_id=%s | session_id=%s | reason=%s | ip=%s',
                request.user.email,
                request.user.member.id,
                token,
                str(exc),
                get_client_ip(request),
            )

        return self.render_to_response(context)


# ==================== PHASE 3: MEMBER PAYMENTS HISTORY ====================

class MyPaymentsView(MemberRequiredMixin, ListView):
    """Member's payment history with filtering."""
    template_name = 'gym_management/my_payments.html'
    context_object_name = 'payments'
    paginate_by = 20
    
    def get_queryset(self):
        member = self.request.user.member
        queryset = Payment.objects.filter(
            subscription__member=member
        ).select_related('subscription__plan').order_by('-initiated_at')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(initiated_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(initiated_at__date__lte=end_date)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = self.request.user.member
        
        # Payment summary
        summary = Payment.objects.filter(
            subscription__member=member,
            status='completed'
        ).aggregate(
            total_paid=Sum('amount'),
            total_payments=Count('id')
        )
        
        context['total_paid'] = summary['total_paid'] or 0
        context['total_payments'] = summary['total_payments']
        
        # Preserve filter params
        context['current_status'] = self.request.GET.get('status', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        
        return context
