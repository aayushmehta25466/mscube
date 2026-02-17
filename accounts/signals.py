from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.signals import email_confirmed
from .models import User, Member


@receiver(email_confirmed)
def create_member_profile_on_email_confirmation(sender, request, email_address, **kwargs):
    """
    Automatically create a Member profile when a user confirms their email.
    This ensures only verified users get Member profiles.
    """
    user = email_address.user
    
    # Mark user as verified
    if not user.is_verified:
        user.is_verified = True
        user.save()
    
    # Create Member profile if it doesn't exist and user doesn't have other profiles
    if not hasattr(user, 'member') and \
       not hasattr(user, 'trainer') and \
       not hasattr(user, 'staff') and \
       not hasattr(user, 'adminprofile'):
        Member.objects.create(user=user)


@receiver(post_save, sender=User)
def create_member_for_superuser(sender, instance, created, **kwargs):
    """
    Automatically create Member profile for superusers.
    Superusers can later be promoted to AdminProfile.
    """
    if created and instance.is_superuser:
        # Ensure superuser has a profile
        if not hasattr(instance, 'member'):
            Member.objects.create(user=instance)
