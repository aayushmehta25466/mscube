from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Member, Trainer, Staff, AdminProfile


class MemberInline(admin.StackedInline):
    """Inline admin for Member profile."""
    model = Member
    can_delete = False
    verbose_name_plural = 'Member Profile'
    fk_name = 'user'


class TrainerInline(admin.StackedInline):
    """Inline admin for Trainer profile."""
    model = Trainer
    can_delete = False
    verbose_name_plural = 'Trainer Profile'
    fk_name = 'user'


class StaffInline(admin.StackedInline):
    """Inline admin for Staff profile."""
    model = Staff
    can_delete = False
    verbose_name_plural = 'Staff Profile'
    fk_name = 'user'


class AdminProfileInline(admin.StackedInline):
    """Inline admin for Admin profile."""
    model = AdminProfile
    can_delete = False
    verbose_name_plural = 'Admin Profile'
    fk_name = 'user'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""
    
    list_display = ('username', 'email', 'full_name', 'phone', 'is_verified', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_verified', 'created_at')
    search_fields = ('username', 'email', 'full_name', 'phone')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('full_name', 'email', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'full_name', 'phone', 'password1', 'password2', 'is_verified'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_login', 'date_joined')
    
    # Display inline profiles based on what exists
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    """Admin for Member profiles."""
    
    list_display = ('user', 'get_email', 'get_phone', 'joined_date', 'age', 'is_active')
    list_filter = ('is_active', 'joined_date')
    search_fields = ('user__username', 'user__email', 'user__full_name', 'emergency_contact')
    ordering = ('-joined_date',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Personal Information', {'fields': ('date_of_birth', 'address', 'emergency_contact')}),
        ('Status', {'fields': ('is_active', 'joined_date')}),
    )
    
    readonly_fields = ('joined_date',)
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    
    def get_phone(self, obj):
        return obj.user.phone or '-'
    get_phone.short_description = 'Phone'


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    """Admin for Trainer profiles."""
    
    list_display = ('user', 'get_email', 'specialization', 'experience_years', 'is_active')
    list_filter = ('is_active', 'joined_date', 'experience_years')
    search_fields = ('user__username', 'user__email', 'user__full_name', 'specialization')
    ordering = ('-joined_date',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Trainer Information', {'fields': ('specialization', 'experience_years', 'bio')}),
        ('Personal Information', {'fields': ('date_of_birth', 'address')}),
        ('Status', {'fields': ('is_active', 'joined_date')}),
    )
    
    readonly_fields = ('joined_date',)
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    """Admin for Staff profiles."""
    
    list_display = ('user', 'get_email', 'department', 'is_active')
    list_filter = ('is_active', 'joined_date', 'department')
    search_fields = ('user__username', 'user__email', 'user__full_name', 'department')
    ordering = ('-joined_date',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Staff Information', {'fields': ('department',)}),
        ('Personal Information', {'fields': ('date_of_birth', 'address')}),
        ('Status', {'fields': ('is_active', 'joined_date')}),
    )
    
    readonly_fields = ('joined_date',)
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    """Admin for Admin profiles."""
    
    list_display = ('user', 'get_email', 'access_level', 'can_manage_users', 'can_manage_payments', 'can_view_reports', 'is_active')
    list_filter = ('is_active', 'access_level', 'can_manage_users', 'can_manage_payments', 'can_view_reports')
    search_fields = ('user__username', 'user__email', 'user__full_name')
    ordering = ('-joined_date',)
    
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Permissions', {
            'fields': ('access_level', 'can_manage_users', 'can_manage_payments', 'can_view_reports')
        }),
        ('Personal Information', {'fields': ('date_of_birth', 'address')}),
        ('Status', {'fields': ('is_active', 'joined_date')}),
    )
    
    readonly_fields = ('joined_date',)
    
    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
