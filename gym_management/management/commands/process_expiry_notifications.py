"""
Management command to process subscription expiry notifications.

This command should be run daily via cron or a task scheduler:
    python manage.py process_expiry_notifications

Crontab example (run daily at 8:00 AM):
    0 8 * * * cd /path/to/mscube && /path/to/venv/bin/python manage.py process_expiry_notifications

What this command does:
1. Expires any subscriptions that have passed their end date
2. Creates notifications for subscriptions expiring in 7, 3, and 1 days
3. Sends email notifications if configured
4. Creates dashboard notifications for members
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from gym_management.services import SubscriptionService, NotificationService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process subscription expiry notifications and expire past-due subscriptions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )
        parser.add_argument(
            '--skip-emails',
            action='store_true',
            help='Create notifications but skip sending emails'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_emails = options['skip_emails']
        
        self.stdout.write(f"[{timezone.now()}] Starting expiry notification processing...")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Step 1: Expire past-due subscriptions
        if not dry_run:
            expired_count = SubscriptionService.check_and_expire_subscriptions()
            self.stdout.write(
                self.style.SUCCESS(f"Expired {expired_count} past-due subscription(s)")
            )
        else:
            from gym_management.models import Subscription
            would_expire = Subscription.objects.filter(
                status='active',
                end_date__lt=timezone.localdate()
            ).count()
            self.stdout.write(f"Would expire {would_expire} past-due subscription(s)")
        
        # Step 2: Process notifications
        if not dry_run:
            if skip_emails:
                # Process notifications without sending emails
                stats = self._process_notifications_without_email()
            else:
                stats = NotificationService.process_expiry_notifications()
            
            self.stdout.write(self.style.SUCCESS(
                f"Notifications created: {stats['notifications_created']}"
            ))
            self.stdout.write(self.style.SUCCESS(
                f"Emails sent: {stats['emails_sent']}"
            ))
            if stats['errors'] > 0:
                self.stdout.write(self.style.WARNING(
                    f"Errors encountered: {stats['errors']}"
                ))
        else:
            # Show what would be processed
            self._show_dry_run_preview()
        
        self.stdout.write(
            self.style.SUCCESS(f"[{timezone.now()}] Expiry notification processing complete")
        )

    def _process_notifications_without_email(self):
        """Process notifications but skip email sending."""
        from gym_management.models import Notification
        
        stats = {
            'notifications_created': 0,
            'emails_sent': 0,
            'errors': 0,
        }
        
        for days in NotificationService.EXPIRY_ALERT_DAYS:
            subscriptions = NotificationService.get_expiring_subscriptions(days)
            
            for subscription in subscriptions:
                try:
                    notification = NotificationService.create_expiry_notification(
                        subscription, days, channel='dashboard'  # Dashboard only
                    )
                    
                    if notification:
                        stats['notifications_created'] += 1
                        
                except Exception as e:
                    logger.error(f"Error processing notification: {e}")
                    stats['errors'] += 1
        
        return stats

    def _show_dry_run_preview(self):
        """Show preview of what would be processed in dry run mode."""
        for days in NotificationService.EXPIRY_ALERT_DAYS:
            subscriptions = NotificationService.get_expiring_subscriptions(days)
            count = subscriptions.count()
            
            if count > 0:
                self.stdout.write(f"\nSubscriptions expiring in {days} day(s): {count}")
                for sub in subscriptions[:5]:  # Show first 5
                    self.stdout.write(
                        f"  - {sub.member.user.full_name} ({sub.plan.name}) - "
                        f"expires {sub.end_date}"
                    )
                if count > 5:
                    self.stdout.write(f"  ... and {count - 5} more")
