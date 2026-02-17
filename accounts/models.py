from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from datetime import date

class UserManager(BaseUserManager):
    """Custom user manager for User model without username field."""
    
    def create_user(self, email, full_name, password=None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        if not email:
            raise ValueError('The Email field must be set')
        if not full_name:
            raise ValueError('The Full Name field must be set')
        
        email = self.normalize_email(email)
        # Auto-generate username from email if not provided
        if 'username' not in extra_fields or not extra_fields['username']:
            extra_fields['username'] = email.split('@')[0]
        
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, full_name, password=None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, full_name, password, **extra_fields)


class User(AbstractUser):
    """Custom User model with email and phone authentication."""
    
    # Override to make email required and unique
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    
    # Phone validator (optional field)
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone = models.CharField(validators=[phone_regex], max_length=17, blank=True, null=True)
    
    # Verification fields
    is_verified = models.BooleanField(default=False, help_text="Designates whether this user has verified their email.")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'full_name']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.email or self.username
    
    def save(self, *args, **kwargs):
        # Auto-generate username from email if not set
        if not self.username and self.email:
            self.username = self.email.split('@')[0]
        super().save(*args, **kwargs)


# ==================== PROFILE MODELS ====================

class BaseProfile(models.Model):
    """Abstract base model for all profile types."""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='%(class)s')
    date_of_birth = models.DateField(null=True, blank=True)
    joined_date = models.DateField(auto_now_add=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
    
    @property
    def age(self):
        """Calculate age from date_of_birth."""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    def __str__(self):
        return f"{self.user.full_name} ({self.__class__.__name__})"


class Member(BaseProfile):
    """Member profile for gym members."""
    
    emergency_contact = models.CharField(max_length=150, blank=True, help_text="Emergency contact name and phone")
    
    class Meta:
        db_table = 'members'
        verbose_name = 'Member'
        verbose_name_plural = 'Members'


class Trainer(BaseProfile):
    """Trainer profile for gym trainers."""
    
    specialization = models.CharField(max_length=200, help_text="e.g., Weight Training, Yoga, CrossFit")
    experience_years = models.PositiveIntegerField(default=0, help_text="Years of experience")
    bio = models.TextField(blank=True, help_text="Trainer biography and qualifications")
    
    class Meta:
        db_table = 'trainers'
        verbose_name = 'Trainer'
        verbose_name_plural = 'Trainers'


class Staff(BaseProfile):
    """Staff profile for gym staff members."""
    
    department = models.CharField(max_length=100, help_text="e.g., Front Desk, Maintenance, Sales")
    
    class Meta:
        db_table = 'staff'
        verbose_name = 'Staff'
        verbose_name_plural = 'Staff'


class AdminProfile(BaseProfile):
    """Admin profile for gym administrators with granular permissions."""
    
    ACCESS_LEVEL_CHOICES = [
        ('full', 'Full Access'),
        ('limited', 'Limited Access'),
    ]
    
    access_level = models.CharField(max_length=20, choices=ACCESS_LEVEL_CHOICES, default='limited')
    can_manage_users = models.BooleanField(default=False, help_text="Can create, update, delete users")
    can_manage_payments = models.BooleanField(default=False, help_text="Can manage payments and subscriptions")
    can_view_reports = models.BooleanField(default=False, help_text="Can view analytics and reports")
    
    class Meta:
        db_table = 'admin_profiles'
        verbose_name = 'Admin Profile'
        verbose_name_plural = 'Admin Profiles'
